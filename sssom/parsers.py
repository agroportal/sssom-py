import logging
import os
import re
from typing import Dict
from xml.dom import minidom, Node
from xml.dom.minidom import Document

import pandas as pd
import yaml
from rdflib import Graph

from .sssom_document import MappingSet, Mapping, MappingSetDocument
from .util import get_file_extension, RDF_FORMATS

cwd = os.path.abspath(os.path.dirname(__file__))


# Readers (from file)


def from_tsv(filename: str, curie_map: Dict[str, str] = None, meta: Dict[str, str] = None) -> MappingSetDocument:
    """
    parses a TSV to a MappingSetDocument
    """

    df = read_pandas(filename)
    if meta is None:
        meta = _read_metadata_from_table(filename)
    if 'curie_map' in meta:
        logging.info("Context provided, but SSSOM file provides its own CURIE map. "
                     "CURIE map from context is disregarded.")
        curie_map = meta['curie_map']
    return from_dataframe(df, curie_map=curie_map, meta=meta)


def from_rdf(filename: str, curie_map: Dict[str, str] = None, meta: Dict[str, str] = None) -> MappingSetDocument:
    """
        parses a TSV to a MappingSetDocument
        """
    g = Graph()
    file_format = guess_file_format(filename)
    g.parse(filename, format=file_format)
    return from_rdf_graph(g, curie_map, meta)


def from_owl(filename: str, curie_map: Dict[str, str] = None, meta: Dict[str, str] = None) -> MappingSetDocument:
    """
        parses a TSV to a MappingSetDocument
        """
    g = Graph()
    file_format = guess_file_format(filename)
    g.parse(filename, format=file_format)
    return from_owl_graph(g, curie_map, meta)


def guess_file_format(filename):
    extension = get_file_extension(filename)
    if extension in ["owl", "rdf"]:
        return "xml"
    elif extension in RDF_FORMATS:
        return extension
    else:
        raise Exception(f"File extension {extension} does not correspond to a legal file format")


def from_alignment_xml(filename: str, curie_map: Dict[str, str] = None,
                       meta: Dict[str, str] = None) -> MappingSetDocument:
    """
           parses a TSV to a MappingSetDocument
           """

    xmldoc = minidom.parse(filename)
    return from_alignment_minidom(xmldoc, curie_map, meta)


def from_alignment_minidom(dom: Document, curie_map: Dict[str, str] = None,
                           meta: Dict[str, str] = None) -> MappingSetDocument:
    """
    Reads a minidom Document object
    :param dom: XML (minidom) object
    :param curie_map:
    :param meta: Optional meta data
    :return: MappingSetDocument
    """
    if not curie_map:
        raise Exception(f'No valid curie_map provided')

    ms = MappingSet()
    mlist = []
    bad_attrs = {}

    alignments = dom.getElementsByTagName('Alignment')
    for n in alignments:
        for e in n.childNodes:
            if e.nodeType == Node.ELEMENT_NODE:
                node_name = e.nodeName
                if node_name == "map":
                    cell = e.getElementsByTagName('Cell')
                    for c_node in cell:
                        m = _prepare_mapping(_cell_element_values(c_node, curie_map))
                        mlist.append(m)
                elif node_name == "xml":
                    if e.firstChild.nodeValue != "yes":
                        raise Exception(
                            f"Alignment format: xml element said, but not set to yes. Only XML is supported!")
                elif node_name == "onto1":
                    ms["subject_source_id"] = e.firstChild.nodeValue
                elif node_name == "onto2":
                    ms["object_source_id"] = e.firstChild.nodeValue
                elif node_name == "uri1":
                    ms["subject_source"] = e.firstChild.nodeValue
                elif node_name == "uri2":
                    ms["object_source"] = e.firstChild.nodeValue

    ms.mappings = mlist
    if meta:
        for k, v in meta.items():
            if k != 'curie_map':
                ms[k] = v
    return MappingSetDocument(mapping_set=ms, curie_map=curie_map)


# Readers (from object)

def from_dataframe(df: pd.DataFrame, curie_map: Dict[str, str], meta: Dict[str, str]) -> MappingSetDocument:
    """
    Converts a dataframe to a MappingSetDocument
    :param df:
    :param curie_map:
    :param meta:
    :return: MappingSetDocument
    """
    if not curie_map:
        raise Exception(f'No valid curie_map provided')

    mlist = []
    ms = MappingSet()
    bad_attrs = {}
    for _, row in df.iterrows():
        mdict = {}
        for k, v in row.items():
            ok = False
            if k:
                k = str(k)
            # if k.endswith('_id'): # TODO: introspect
            #    v = Entity(id=v)
            if hasattr(Mapping, k):
                mdict[k] = v
                ok = True
            if hasattr(MappingSet, k):
                ms[k] = v
                ok = True
            if not ok:
                if k not in bad_attrs:
                    bad_attrs[k] = 1
                else:
                    bad_attrs[k] += 1
        # logging.info(f'Row={mdict}')
        m = _prepare_mapping(Mapping(**mdict))
        mlist.append(m)
    for k, v in bad_attrs.items():
        logging.warning(f'No attr for {k} [{v} instances]')
    ms.mappings = mlist
    for k, v in meta.items():
        if k != 'curie_map':
            ms[k] = v
    return MappingSetDocument(mapping_set=ms, curie_map=curie_map)


def from_owl_graph(g: Graph, curie_map: Dict[str, str], meta: Dict[str, str]) -> MappingSetDocument:
    """
    Converts a dataframe to a MappingSetDocument
    :param g: A Graph object (rdflib)
    :param curie_map:
    :param meta: an optional set of metadata elements
    :return: MappingSetDocument
    """
    if not curie_map:
        raise Exception(f'No valid curie_map provided')

    ms = MappingSet()
    return MappingSetDocument(mapping_set=ms, curie_map=curie_map)


def from_rdf_graph(g: Graph, curie_map: Dict[str, str], meta: Dict[str, str]) -> MappingSetDocument:
    """
    Converts a dataframe to a MappingSetDocument
    :param g: A Graph object (rdflib)
    :param curie_map:
    :param meta: an optional set of metadata elements
    :return: MappingSetDocument
    """
    if not curie_map:
        raise Exception(f'No valid curie_map provided')

    ms = MappingSet()
    return MappingSetDocument(mapping_set=ms, curie_map=curie_map)


# Utilities (reading)


def get_parsing_function(input_format, filename):
    if input_format is None:
        input_format = get_file_extension(filename)
    if input_format == 'tsv':
        return from_tsv
    elif input_format == 'rdf':
        return from_rdf
    elif input_format == 'alignment-api-xml':
        return from_alignment_xml
    else:
        raise Exception(f'Unknown input format: {input_format}')


def read_pandas(filename: str, sep=None) -> pd.DataFrame:
    """
    wrapper to pd.read_csv that handles comment lines correctly
    :param filename:
    :param sep: File separator in pandas (\t or ,)
    :return:
    """
    if not sep:
        extension = get_file_extension(filename)
        sep = "\t"
        if extension == "tsv":
            sep = "\t"
        elif extension == "csv":
            sep = ","
        else:
            logging.warning(f"Cannot automatically determine table format, trying tsv.")

    # from tempfile import NamedTemporaryFile
    # with NamedTemporaryFile("r+") as tmp:
    #    with open(filename, "r") as f:
    #        for line in f:
    #            if not line.startswith('#'):
    #                tmp.write(line + "\n")
    #    tmp.seek(0)
    return pd.read_csv(filename, comment='#', sep=sep).fillna("")


def _prepare_mapping(mapping: Mapping):
    p = mapping.predicate_id
    if p == "sssom:superClassOf":
        mapping.predicate_id = "rdfs:subClassOf"
        return _swap_object_subject(mapping)
    return mapping


def _swap_object_subject(mapping):
    members = [attr.replace("subject_", "") for attr in dir(mapping) if
               not callable(getattr(mapping, attr)) and not attr.startswith("__") and attr.startswith("subject_")]
    for var in members:
        subject_val = getattr(mapping, "subject_" + var)
        object_val = getattr(mapping, "object_" + var)
        setattr(mapping, "subject_" + var, object_val)
        setattr(mapping, "object_" + var, subject_val)
    return mapping


def _read_metadata_from_table(filename: str):
    with open(filename, 'r') as s:
        yamlstr = ""
        for line in s:
            if line.startswith("#"):
                yamlstr += re.sub('^#', '', line)
            else:
                break
        if yamlstr:
            meta = yaml.safe_load(yamlstr)
            logging.info(f'Meta={meta}')
            return meta
    return {}


def is_valid_mapping(m):
    return True


def curie(uri: str, curie_map):
    for prefix in curie_map:
        uri_prefix = curie_map[prefix]
        if uri.startswith(uri_prefix):
            remainder = uri.replace(uri_prefix, "")
            return f"{prefix}:{remainder}"
    return uri


def _cell_element_values(cell_node, curie_map: dict) -> Mapping:
    mdict = {}
    for child in cell_node.childNodes:
        if child.nodeType == Node.ELEMENT_NODE:
            if child.nodeName == "entity1":
                mdict["subject_id"] = curie(child.getAttribute('rdf:resource'), curie_map)
            elif child.nodeName == "entity2":
                mdict["object_id"] = curie(child.getAttribute('rdf:resource'), curie_map)
            elif child.nodeName == "measure":
                mdict["confidence"] = child.firstChild.nodeValue
            elif child.nodeName == "relation":
                relation = child.firstChild.nodeValue
                if relation == "=":
                    mdict["predicate_id"] = "owl:equivalentClass"
                else:
                    logging.warning(f"{relation} not a recognised relation type.")
            else:
                logging.warning(f"Unsupported alignment api element: {child.nodeName}")
    m = Mapping(**mdict)
    if is_valid_mapping(m):
        return m