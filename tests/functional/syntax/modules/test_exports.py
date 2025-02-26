import pytest

from vyper.compiler import compile_code
from vyper.exceptions import (
    ImmutableViolation,
    InterfaceViolation,
    NamespaceCollision,
    StructureException,
)

from .helpers import NONREENTRANT_NOTE


def test_exports_no_uses(make_input_bundle):
    lib1 = """
counter: uint256

@external
def get_counter() -> uint256:
    self.counter += 1
    return self.counter
    """
    main = """
import lib1
exports: lib1.get_counter
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(ImmutableViolation) as e:
        compile_code(main, input_bundle=input_bundle)

    assert e.value._message == "Cannot access `lib1` state!" + NONREENTRANT_NOTE

    expected_hint = "add `uses: lib1` or `initializes: lib1` as a "
    expected_hint += "top-level statement to your contract"
    assert e.value.hint == expected_hint


def test_exports_no_uses_variable(make_input_bundle):
    lib1 = """
counter: public(uint256)
    """
    main = """
import lib1
exports: lib1.counter
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(ImmutableViolation) as e:
        compile_code(main, input_bundle=input_bundle)

    assert e.value._message == "Cannot access `lib1` state!" + NONREENTRANT_NOTE

    expected_hint = "add `uses: lib1` or `initializes: lib1` as a "
    expected_hint += "top-level statement to your contract"
    assert e.value.hint == expected_hint


def test_exports_uses_variable(make_input_bundle):
    lib1 = """
counter: public(uint256)
    """
    main = """
import lib1

exports: lib1.counter
initializes: lib1
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    assert compile_code(main, input_bundle=input_bundle) is not None


def test_exports_uses(make_input_bundle):
    lib1 = """
counter: uint256

@external
def get_counter() -> uint256:
    self.counter += 1
    return self.counter
    """
    main = """
import lib1

exports: lib1.get_counter
initializes: lib1
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    assert compile_code(main, input_bundle=input_bundle) is not None


# test that exporting can satisfy an implements constraint
# use a mix of public variables and functions
def test_exports_implements(make_input_bundle):
    token_interface = """
@external
@view
def totalSupply() -> uint256:
    ...

@external
@view
def balanceOf(addr: address) -> uint256:
    ...

@external
def transfer(receiver: address, amount: uint256):
    ...
    """
    lib1 = """
import itoken

implements: itoken

@deploy
def __init__(initial_supply: uint256):
    self.totalSupply = initial_supply
    self.balanceOf[msg.sender] = initial_supply

totalSupply: public(uint256)
balanceOf: public(HashMap[address, uint256])

@external
def transfer(receiver: address, amount: uint256):
    self.balanceOf[msg.sender] -= amount
    self.balanceOf[receiver] += amount
    """
    main = """
import tokenlib
import itoken

implements: itoken
exports: (tokenlib.totalSupply, tokenlib.balanceOf, tokenlib.transfer)

initializes: tokenlib

@deploy
def __init__():
    tokenlib.__init__(100_000_000)
    """
    input_bundle = make_input_bundle({"tokenlib.vy": lib1, "itoken.vyi": token_interface})
    assert compile_code(main, input_bundle=input_bundle) is not None


# test that exporting can satisfy an implements constraint
# use a mix of local and imported functions
def test_exports_implements2(make_input_bundle):
    ifoobar = """
@external
def foo():
    ...

@external
def bar():
    ...
    """
    lib1 = """
import ifoobar

implements: ifoobar

counter: uint256

@external
def foo():
    pass

@external
def bar():
    self.counter += 1
    """
    main = """
import lib1
import ifoobar

implements: ifoobar
exports: lib1.foo

initializes: lib1

# for fun, export a different function with the same name
@external
def bar():
    lib1.counter += 2
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1, "ifoobar.vyi": ifoobar})
    assert compile_code(main, input_bundle=input_bundle) is not None


def test_function_name_collisions(make_input_bundle):
    lib1 = """
@external
def foo():
    pass
    """
    main = """
import lib1

exports: lib1.foo

@external
def foo():
    x: uint256 = 12345
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(NamespaceCollision) as e:
        # TODO: make the error message reference the export
        compile_code(main, contract_path="main.vy", input_bundle=input_bundle)

    assert e.value._message == "Member 'foo' already exists in self"

    assert e.value.annotations[0].lineno == 4
    assert e.value.annotations[0].node_source_code == "lib1.foo"
    assert e.value.annotations[0].module_node.path == "main.vy"

    assert e.value.prev_decl.lineno == 7
    assert e.value.prev_decl.node_source_code.startswith("def foo():")
    assert e.value.prev_decl.module_node.path == "main.vy"


def test_duplicate_exports(make_input_bundle):
    lib1 = """
@external
def foo():
    pass

@external
def bar():
    pass
    """
    main = """
import lib1

exports: lib1.foo
exports: lib1.bar
exports: lib1.foo
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(StructureException) as e:
        # TODO: make the error message reference the export
        compile_code(main, contract_path="main.vy", input_bundle=input_bundle)

    assert e.value._message == "already exported!"

    assert e.value.annotations[0].lineno == 6
    assert e.value.annotations[0].node_source_code == "lib1.foo"
    assert e.value.annotations[0].module_node.path == "main.vy"

    assert e.value.prev_decl.lineno == 4
    assert e.value.prev_decl.node_source_code == "lib1.foo"
    assert e.value.prev_decl.module_node.path == "main.vy"


def test_duplicate_exports_tuple(make_input_bundle):
    lib1 = """
@external
def foo():
    pass

@external
def bar():
    pass
    """
    main = """
import lib1

exports: (lib1.foo, lib1.bar, lib1.foo)
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(StructureException) as e:
        # TODO: make the error message reference the export
        compile_code(main, contract_path="main.vy", input_bundle=input_bundle)

    assert e.value._message == "already exported!"

    assert e.value.annotations[0].lineno == 4
    assert e.value.annotations[0].col_offset == 30
    assert e.value.annotations[0].node_source_code == "lib1.foo"
    assert e.value.annotations[0].module_node.path == "main.vy"

    assert e.value.prev_decl.lineno == 4
    assert e.value.prev_decl.col_offset == 10
    assert e.value.prev_decl.node_source_code == "lib1.foo"
    assert e.value.prev_decl.module_node.path == "main.vy"


def test_duplicate_exports_tuple2(make_input_bundle):
    lib1 = """
@external
def foo():
    pass

@external
def bar():
    pass
    """
    main = """
import lib1

exports: lib1.foo
exports: (lib1.bar, lib1.foo)
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(StructureException) as e:
        # TODO: make the error message reference the export
        compile_code(main, contract_path="main.vy", input_bundle=input_bundle)

    assert e.value._message == "already exported!"

    assert e.value.annotations[0].lineno == 5
    assert e.value.annotations[0].col_offset == 20
    assert e.value.annotations[0].node_source_code == "lib1.foo"
    assert e.value.annotations[0].module_node.path == "main.vy"

    assert e.value.prev_decl.lineno == 4
    assert e.value.prev_decl.col_offset == 9
    assert e.value.prev_decl.node_source_code == "lib1.foo"
    assert e.value.prev_decl.module_node.path == "main.vy"


def test_interface_export_collision(make_input_bundle):
    main = """
import lib1

exports: lib1.__interface__
exports: lib1.bar
    """
    lib1 = """
@external
def bar() -> uint256:
    return 1
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(StructureException) as e:
        compile_code(main, input_bundle=input_bundle)
    assert e.value._message == "already exported!"


def test_no_export_missing_function(make_input_bundle):
    ifoo = """
@external
def do_xyz():
    ...
    """
    lib1 = """
import ifoo

@external
@view
def bar() -> uint256:
    return 1
    """
    main = """
import lib1

exports: lib1.ifoo
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1, "ifoo.vyi": ifoo})
    with pytest.raises(InterfaceViolation) as e:
        compile_code(main, input_bundle=input_bundle)
    assert e.value._message == "requested `lib1.ifoo` but `lib1` does not implement `lib1.ifoo`!"


def test_no_export_unimplemented_interface(make_input_bundle):
    ifoo = """
@external
def do_xyz():
    ...
    """
    lib1 = """
import ifoo

# technically implements ifoo, but missing `implements: ifoo`

@external
def do_xyz():
    pass
    """
    main = """
import lib1

exports: lib1.ifoo
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1, "ifoo.vyi": ifoo})
    with pytest.raises(InterfaceViolation) as e:
        compile_code(main, input_bundle=input_bundle)
    assert e.value._message == "requested `lib1.ifoo` but `lib1` does not implement `lib1.ifoo`!"


def test_no_export_unimplemented_inline_interface(make_input_bundle):
    lib1 = """
interface ifoo:
    def do_xyz(): nonpayable

# technically implements ifoo, but missing `implements: ifoo`

@external
def do_xyz():
    pass
    """
    main = """
import lib1

exports: lib1.ifoo
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(InterfaceViolation) as e:
        compile_code(main, input_bundle=input_bundle)
    assert e.value._message == "requested `lib1.ifoo` but `lib1` does not implement `lib1.ifoo`!"


def test_export_selector_conflict(make_input_bundle):
    ifoo = """
@external
def gsf():
    ...
    """
    lib1 = """
import ifoo

@external
def gsf():
    pass

@external
@view
def tgeo() -> uint256:
    return 1
    """
    main = """
import lib1

exports: (lib1.ifoo, lib1.tgeo)
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1, "ifoo.vyi": ifoo})
    with pytest.raises(StructureException) as e:
        compile_code(main, input_bundle=input_bundle)
    assert e.value._message == "Methods produce colliding method ID `0x67e43e43`: gsf(), tgeo()"


def test_export_different_return_type(make_input_bundle):
    ifoo = """
@external
def foo() -> uint256:
    ...
    """
    lib1 = """
import ifoo

foo: public(int256)

@deploy
def __init__():
    self.foo = -1
    """
    main = """
import lib1

initializes: lib1

exports: lib1.ifoo

@deploy
def __init__():
    lib1.__init__()
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1, "ifoo.vyi": ifoo})
    with pytest.raises(InterfaceViolation) as e:
        compile_code(main, input_bundle=input_bundle)
    assert e.value._message == "requested `lib1.ifoo` but `lib1` does not implement `lib1.ifoo`!"


def test_export_empty_interface(make_input_bundle, tmp_path):
    lib1 = """
def an_internal_function():
    pass
    """
    main = """
import lib1

exports: lib1.__interface__
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})
    with pytest.raises(StructureException) as e:
        compile_code(main, input_bundle=input_bundle)

    # as_posix() for windows
    lib1_path = (tmp_path / "lib1.vy").as_posix()
    assert e.value._message == f"lib1 (located at `{lib1_path}`) has no external functions!"


def test_invalid_export(make_input_bundle):
    lib1 = """
@external
def foo():
    pass
    """
    main = """
import lib1
a: address

exports: lib1.__interface__(self.a).foo
    """
    input_bundle = make_input_bundle({"lib1.vy": lib1})

    with pytest.raises(StructureException) as e:
        compile_code(main, input_bundle=input_bundle)

    assert e.value._message == "invalid export of a value"
    assert e.value._hint == "exports should look like <module>.<function | interface>"

    main = """
interface Foo:
    def foo(): nonpayable

exports: Foo
    """
    with pytest.raises(StructureException) as e:
        compile_code(main)

    assert e.value._message == "invalid export"
    assert e.value._hint == "exports should look like <module>.<function | interface>"


@pytest.mark.parametrize("exports_item", ["__at__", "__at__(self)", "__at__(self).__interface__"])
def test_invalid_at_exports(get_contract, make_input_bundle, exports_item):
    lib = """
@external
@view
def foo() -> uint256:
    return 5
    """

    main = f"""
import lib

exports: lib.{exports_item}

@external
@view
def bar() -> uint256:
    return staticcall lib.__at__(self).foo()
    """
    input_bundle = make_input_bundle({"lib.vy": lib})

    with pytest.raises(Exception) as e:
        compile_code(main, input_bundle=input_bundle)

    if exports_item == "__at__":
        assert "not a function or interface" in str(e.value)
    if exports_item == "__at__(self)":
        assert "invalid exports" in str(e.value)
    if exports_item == "__at__(self).__interface__":
        assert "has no member '__interface__'" in str(e.value)
