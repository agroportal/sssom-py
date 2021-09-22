import json
import logging
import os
from typing import Any, Callable, Dict, Optional, TextIO, Tuple

import pandas as pd
import yaml
from jsonasobj import as_json_obj
from jsonasobj2 import JsonObj
from linkml_runtime.dumpers import JSONDumper
from linkml_runtime.utils.yamlutils import as_json_object as yaml_to_json
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from .parsers import to_mapping_set_document
from .sssom_datamodel import slots
from .util import (
    RDF_FORMATS,
    SSSOM_DEFAULT_RDF_SERIALISATION,
    SSSOM_URI_PREFIX,
    URI_SSSOM_MAPPINGS,
    MappingSetDataFrame,
    get_file_extension,
    prepare_context_from_curie_map,
)

# noinspection PyProtectedMember

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
OWL_OBJECT_PROPERTY = "http://www.w3.org/2002/07/owl#ObjectProperty"
OWL_ANNOTATION_PROPERTY = "http://www.w3.org/2002/07/owl#AnnotationProperty"
OWL_CLASS = "http://www.w3.org/2002/07/owl#Class"
OWL_EQUIV_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"
OWL_EQUIV_OBJECTPROPERTY = "http://www.w3.org/2002/07/owl#equivalentProperty"
SSSOM_NS = SSSOM_URI_PREFIX

# Writers

MSDFWriter = Callable[[MappingSetDataFrame, TextIO], None]


def write_table(msdf: MappingSetDataFrame, file: TextIO, serialisation="tsv") -> None:
    """
    dataframe 2 tsv
    """
    if msdf.df is None:
        raise TypeError

    sep = _get_separator(serialisation)

    # df = to_dataframe(msdf)

    meta: Dict[str, Any] = {}
    if msdf.metadata is not None:
        meta.update(msdf.metadata)
    if msdf.prefixmap is not None:
        meta["curie_map"] = msdf.prefixmap

    lines = yaml.safe_dump(meta).split("\n")
    lines = [f"# {line}" for line in lines if line != ""]
    s = msdf.df.to_csv(sep=sep, index=False)
    lines = lines + [s]
    for line in lines:
        print(line, file=file)


def write_rdf(
    msdf: MappingSetDataFrame,
    file: TextIO,
    serialisation: Optional[str] = None,
) -> None:
    """
    dataframe 2 tsv
    """
    if serialisation is None:
        serialisation = SSSOM_DEFAULT_RDF_SERIALISATION
    elif serialisation not in RDF_FORMATS:
        logging.warning(
            f"Serialisation {serialisation} is not supported, "
            f"using {SSSOM_DEFAULT_RDF_SERIALISATION} instead."
        )
        serialisation = SSSOM_DEFAULT_RDF_SERIALISATION

    graph = to_rdf_graph(msdf=msdf)
    t = graph.serialize(format=serialisation, encoding="utf-8")
    print(t.decode("utf-8"), file=file)


def write_json(msdf: MappingSetDataFrame, output: TextIO, serialisation="json") -> None:
    """
    dataframe 2 tsv
    """
    if serialisation == "json":
        data = to_json(msdf)
        # doc = to_mapping_set_document(msdf)
        # context = prepare_context_from_curie_map(doc.curie_map)
        # data = JSONDumper().dumps(doc.mapping_set, contexts=context)
        json.dump(data, output, indent=2)

    else:
        raise ValueError(
            f"Unknown json format: {serialisation}, currently only json supported"
        )


def write_owl(
    msdf: MappingSetDataFrame,
    file: TextIO,
    serialisation=SSSOM_DEFAULT_RDF_SERIALISATION,
) -> None:
    if serialisation not in RDF_FORMATS:
        logging.warning(
            f"Serialisation {serialisation} is not supported, "
            f"using {SSSOM_DEFAULT_RDF_SERIALISATION} instead."
        )
        serialisation = SSSOM_DEFAULT_RDF_SERIALISATION

    graph = to_owl_graph(msdf)
    t = graph.serialize(format=serialisation, encoding="utf-8")
    print(t.decode("utf-8"), file=file)


# Converters
# Converters convert a mappingsetdataframe to an object of the supportes types (json, pandas dataframe)


def to_dataframe(msdf: MappingSetDataFrame) -> pd.DataFrame:
    data = []
    doc = to_mapping_set_document(msdf)
    if doc.mapping_set.mappings is None:
        raise TypeError
    for mapping in doc.mapping_set.mappings:
        mdict = mapping.__dict__
        m = {}
        for key in mdict:
            if mdict[key]:
                m[key] = mdict[key]
        data.append(m)
    df = pd.DataFrame(data=data)
    return df


def to_owl_graph(msdf: MappingSetDataFrame) -> Graph:
    """

    Args:
        msdf: The MappingSetDataFrame (SSSOM table)

    Returns:
        an rdfib Graph obect

    """

    graph = to_rdf_graph(msdf=msdf)

    # if MAPPING_SET_ID in msdf.metadata:
    #    mapping_set_id = msdf.metadata[MAPPING_SET_ID]
    # else:
    #    mapping_set_id = DEFAULT_MAPPING_SET_ID

    sparql_prefixes = """
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX IAO: <http://purl.obolibrary.org/obo/IAO_>
PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>

"""
    queries = []

    queries.append(
        sparql_prefixes
        + """
    INSERT {
      ?c rdf:type owl:Class .
      ?d rdf:type owl:Class .
    }
    WHERE {
     ?c owl:equivalentClass ?d .
    }
    """
    )

    queries.append(
        sparql_prefixes
        + """
        INSERT {
          ?c rdf:type owl:ObjectProperty .
          ?d rdf:type owl:ObjectProperty .
        }
        WHERE {
         ?c owl:equivalentProperty ?d .
        }
        """
    )

    queries.append(
        sparql_prefixes
        + """
    DELETE {
      ?o rdf:type sssom:MappingSet .
    }
    INSERT {
      ?o rdf:type owl:Ontology .
    }
    WHERE {
     ?o rdf:type sssom:MappingSet .
    }
    """
    )

    queries.append(
        sparql_prefixes
        + """
    DELETE {
      ?o sssom:mappings ?mappings .
    }
    WHERE {
     ?o sssom:mappings ?mappings .
    }
    """
    )

    queries.append(
        sparql_prefixes
        + """
    INSERT {
        ?p rdf:type owl:AnnotationProperty .
    }
    WHERE {
        ?o a owl:Axiom ;
        ?p ?v .
        FILTER(?p!=rdf:type && ?p!=owl:annotatedProperty && ?p!=owl:annotatedTarget && ?p!=owl:annotatedSource)
    }
    """
    )

    for query in queries:
        graph.update(query)

    return graph


def to_rdf_graph(msdf: MappingSetDataFrame) -> Graph:
    """

    Args:
        msdf:

    Returns:

    """
    doc = to_mapping_set_document(msdf)
    cntxt = prepare_context_from_curie_map(doc.curie_map)

    # json_obj = to_json(msdf)
    # g = Graph()
    # g.load(json_obj, format="json-ld")
    # print(g.serialize(format="xml"))

    graph = _temporary_as_rdf_graph(
        element=doc.mapping_set, contexts=cntxt, namespaces=doc.curie_map
    )
    # print(graph.serialize(format="turtle").decode())
    return graph


def _temporary_as_rdf_graph(element, contexts, namespaces=None) -> Graph:
    # TODO needs to be replaced by RDFDumper().as_rdf_graph(element=doc.mapping_set, contexts=cntxt)
    # graph = RDFDumper().as_rdf_graph(element=element, contexts=contexts)

    graph = Graph()
    jsonld = json.dumps(as_json_obj(yaml_to_json(element, contexts)))
    graph.parse(data=jsonld, format="json-ld")

    # Adding some stuff that the default RDF serialisation does not do:
    # Direct triples

    for k, v in namespaces.items():
        graph.bind(k, v)

    # TODO replace with graph.objects()
    for _s, _p, o in graph.triples((None, URIRef(URI_SSSOM_MAPPINGS), None)):
        graph.add((o, URIRef(RDF_TYPE), OWL.Axiom))

    for axiom in graph.subjects(RDF.type, OWL.Axiom):
        for p in graph.objects(subject=axiom, predicate=OWL.annotatedProperty):
            for s in graph.objects(subject=axiom, predicate=OWL.annotatedSource):
                for o in graph.objects(subject=axiom, predicate=OWL.annotatedTarget):
                    graph.add((s, p, o))
    return graph


def _tmp_as_rdf_graph(graph, jsonobj):
    return graph

    # for m in doc.mapping_set.mappings:
    #    graph.add( (URIRef(m.subject_id), URIRef(m.predicate_id), URIRef(m.object_id)))


def to_json(msdf: MappingSetDataFrame) -> JsonObj:
    """

    Args:
        msdf: A SSSOM Data Table

    Returns:
        The standard SSSOM json representation
    """

    doc = to_mapping_set_document(msdf)
    context = prepare_context_from_curie_map(doc.curie_map)
    data = JSONDumper().dumps(doc.mapping_set, contexts=context)
    json_obj = json.loads(data)
    return json_obj


# Support methods


def get_writer_function(
    *, output_format: Optional[str] = None, output: TextIO
) -> Tuple[MSDFWriter, str]:
    if output_format is None:
        output_format = get_file_extension(output)

    if output_format == "tsv":
        return write_table, output_format
    elif output_format in RDF_FORMATS:
        return write_rdf, output_format
    elif output_format == "rdf":
        return write_rdf, SSSOM_DEFAULT_RDF_SERIALISATION
    elif output_format == "json":
        return write_json, output_format
    elif output_format == "owl":
        return write_owl, SSSOM_DEFAULT_RDF_SERIALISATION
    else:
        raise ValueError(f"Unknown output format: {output_format}")


def write_tables(sssom_dict, output_dir) -> None:
    for split_id, msdf in sssom_dict.items():
        path = os.path.join(output_dir, f"{split_id}.sssom.tsv")
        with open(path, "w") as file:
            write_table(msdf, file)
        logging.info(f"Writing {path} complete!")


def _inject_annotation_properties(graph: Graph, elements) -> None:
    for var in [
        slot
        for slot in dir(slots)
        if not callable(getattr(slots, slot)) and not slot.startswith("__")
    ]:
        slot = getattr(slots, var)
        if slot.name in elements:
            if slot.uri.startswith(SSSOM_NS):
                graph.add(
                    (
                        URIRef(slot.uri),
                        URIRef(RDF_TYPE),
                        URIRef(OWL_ANNOTATION_PROPERTY),
                    )
                )


def _get_separator(serialisation: Optional[str] = None) -> str:
    if serialisation == "csv":
        sep = ","
    elif serialisation == "tsv" or serialisation is None:
        sep = "\t"
    else:
        raise ValueError(
            f"Unknown table format: {serialisation}, should be one of tsv or csv"
        )
    return sep
