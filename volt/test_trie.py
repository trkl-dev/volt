import logging
from volt import trie

log = logging.getLogger("volt.test.py")
log.setLevel(logging.DEBUG)

def handler():
    log.debug("handler called")


def test_trie():
    root = trie.Node()
    trie.insert(root, "/something", handler)
    log.debug(f"trie state: {root}")

    trie.insert(root, "/something/else", handler)
    log.debug(f"trie state: {root}")

    trie.insert(root, "/hi/there", handler)
    log.debug(f"trie state: {root}")

    assert root.children[0].segment == "something"
    assert root.children[0].children[0].segment == "else"


def test_trie_root_path():
    root = trie.Node()
    trie.insert(root, "/", handler)

    assert len(root.children) == 0
    assert root.handler == handler
