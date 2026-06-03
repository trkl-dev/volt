from collections.abc import Iterable, Iterator
from dataclasses import dataclass, asdict
import logging
from pathlib import Path
from typing import TypedDict, override
from jinja2 import Environment, FileSystemLoader, meta
from jinja2.nodes import Block, For, Getattr, Name, Node, Tuple

from volt import config

log = logging.getLogger("volt.generator.py")


class Field:
    name: str
    type: str | None

    def __init__(self, name: str, type: str | None = None) -> None:
        self.name = name
        self.type = type

    @override
    def __repr__(self) -> str:
        return f"Field<{self.name}|{self.type if self.type is not None else "Any"}>"


# @dataclass
class GeneratedComponent:
    name: str
    template_name: str
    block_name: str
    parent_components: list[str]
    fields: list[Field]

    def __init__(
        self,
        name: str,
        template_name: str | None = None,
        block_name: str | None = None,
        parent_components: list[str] | None = None,
        fields: list[Field] | None = None,
    ) -> None:
        self.name = name
        self.template_name = name

        if block_name is not None:
            self.block_name = block_name

        if parent_components is not None:
            self.parent_components = parent_components
        else:
            self.parent_components = []

        if fields is None:
            self.fields = []
        else:
            self.fields = fields


    @override
    def __repr__(self) -> str:
        return f"Component: {self.name}\n\tblock: {self.block_name}\n\tparents: {self.parent_components}\n\tfields: {"\n\t\t".join(str(f) for f in self.fields)}"

@dataclass
class Context:
    components: list[GeneratedComponent]
    import_types: bool


all_components: list[GeneratedComponent] = []


"""
For each template:
    - get all the referenced templates -> these are also inherited from, as their fields are required also
    - traverse the nodes in the tree
        - 
"""


def get_block_children(
    block: Block, template_name: str, referenced_templates: Iterator[str | None], top_level: bool
) -> Iterable[Block]:
    blocks: list[Block] = []

    child_blocks = block.iter_child_nodes()
    for child_block in child_blocks:
        if not isinstance(child_block, Block):
            continue
        log.debug(f"Inspecting block: {child_block.name}")
        blocks.append(child_block)
        blocks.extend(get_block_children(child_block, template_name, referenced_templates, top_level=False))

    # We want to make sure that we are excluding fields that are captured by parents. Since we are inheriting from
    # these components, we don't want to require them on on the child components as well
    parent_fields: list[Field] = []
    for parent_block in blocks:
        parent_fields.extend(get_block_fields(parent_block))

    fields = [field for field in get_block_fields(block) if field not in parent_fields and field != "loop"]

    # Set the name to just be the name of the block, unless the block is a content block,
    # in which case we name it the file name
    formatted_template_name = template_name_as_title(template_name)
    name = formatted_template_name + name_as_title(block.name)

    parent_components = [formatted_template_name + name_as_title(block.name) for block in blocks]
    # If we have an 'extends' at the top level, we ensure this is added as a parent component to any component
    # at that same 'top level', so as to ensure any fields in extended templates are also required as part of the
    # dataclass context
    if top_level:
        for referenced_template in referenced_templates:
            if referenced_template is None:
                continue
            parent_components.append(name_as_title(referenced_template.replace(".html", "")))

    component = GeneratedComponent(
        name=name,
        template_name=template_name,
        block_name=block.name,
        parent_components=parent_components,
        fields=fields,
    )
    log.debug(f"Adding component: {component}")
    all_components.append(component)
    return blocks


def name_as_title(name: str) -> str:
    name = f"{name.replace('_', ' ').title().replace(' ', '')}"
    return name


def template_name_as_title(template_name: str) -> str:
    return template_name[: template_name.find(".")].title().replace("_", "")


def get_block_fields(block: Block) -> list[Field]:
    fields: list[Field] = []
    for block_body_node in block.body:
        excludes: list[Name] = []
        iterables: list[Name] = []
        # TODO: Vars used in a for loop must be iterable
        # Can we also check if the target has fields, and use those as well?
        # block.
        fors = block.find_all(For)
        for f in fors:
            log.debug("Fors: %s", f)
            ff = f.iter_child_nodes()
            log.debug("Fors block: %s", list(ff))
            # Regular For loop, e.g. for item in items -> item is the target
            if isinstance(f.iter, Name):
                iterables.append(f.iter)
            if isinstance(f.target, Name):
                excludes.append(f.target)
            # Occurs when unpacking as part of a for loop, e.g. for key, value in dict.items() -> (key, value) is the target
            elif isinstance(f.target, Tuple):
                for target in f.target.items:
                    assert isinstance(target, Name)
                    excludes.append(target)
            else:
                raise Exception(f"Unexpected For type: {type(f.target)} for {f.target}")

        r = block_body_node.find_all(Node)
        # log.debug("len(r): %d", len(list(r)))
        for rr in r:
            log.debug("r: %s", rr)
        # TODO: Look at the `For` type and see if vars that are created from for loops can be omitted
        names = block_body_node.find_all(Name)
        for name in names:
            log.debug("name: %s", name)
            skip = False
            for exc in excludes:
                if name.name == exc.name:
                    skip = True
                    break
            if skip:
                continue
            already_exists = False
            if name.ctx == "load":
                for var in fields:
                    if name.name == var["name"]:
                        already_exists = True
                if not already_exists and name.name != "loop":
                    field_type = "Iterable[Any]" if name in iterables else "Any"
                    fields.append(Field(name=name.name, type=field_type))

    return fields


# TODO: Check against templates without blocks
def _generate(environment: Environment, import_types: bool) -> str:
    context = Context(
        components=[],
        import_types=import_types,
    )

    if environment.loader is None:
        raise Exception("No environment loader")

    template_names = environment.list_templates()
    for template_name in template_names:
        log.info(f"Parsing template: {template_name}")
        template_source = environment.loader.get_source(environment, template_name)[0]
        template_ast = environment.parse(template_source)

        # r = template_ast.find_all(DerivedContextReference)
        # log.debug("len(r): %d", len(list(r)))
        # for rr in r:
        #     log.debug("r: %s", rr)

        referenced_templates = meta.find_referenced_templates(template_ast)

        template_blocks: list[Block] = []
        parent_components: list[str] = []
        blocks = template_ast.iter_child_nodes()
        for block in blocks:
            print(block.dump())
            # r = block.find_all(DerivedContextReference)
            # log.debug("len(r): %d", len(list(r)))
            # for rr in r:
            #     log.debug("r: %s", rr)

            if not isinstance(block, Block):
                continue
            log.debug(f"Inspecting block: {block.name}")
            template_blocks.extend(get_block_children(block, template_name, referenced_templates, top_level=True))
            parent_components.append(template_name_as_title(template_name) + name_as_title(block.name))

        name = template_name_as_title(template_name)
        all_components.append(
            GeneratedComponent(
                name=name,
                template_name=template_name,
                block_name="content",
                parent_components=parent_components,
                fields=[],
            )
        )

    # Add all components without parents
    for c in all_components:
        if len(list(c.parent_components)) != 0:
            continue
        context.components.append(c)

    while len(all_components) != len(context.components):
        for c in all_components:
            if c in context.components:
                continue
            if not all(pc in [cc.name for cc in context.components] for pc in c.parent_components):
                continue

            context.components.append(c)

    parent_dir = Path(__file__).parent
    gen_environment = Environment(loader=FileSystemLoader(parent_dir), trim_blocks=True, lstrip_blocks=True)
    template_file = "components.py.j2"
    template = gen_environment.get_template(template_file)
    output = template.render(asdict(context))
    return output


def print_getattr(node: Getattr, current_component: GeneratedComponent) -> None:
    """
    Getattr nodes are for fields that are having an attribute retrieved from them, such as foo.bar
    Getattr nodes can be recursive though, for cases like foo.bar.baz where the structure would be something like
    getattr(getattr(name))
    """
    if isinstance(node.node, Name):
        print(f"Getattr name: {node.node.name}")
    if isinstance(node.node, Getattr):
        print_getattr(node.node, current_component)
    print(f"Getattr attr: {node.attr}")


components: list[GeneratedComponent] = []

def print_indorder(node: Node, current_component: GeneratedComponent) -> None:
    generated_component = None
    if isinstance(node, Block):
        log.info(f"Block: {node.name}")
        generated_component = GeneratedComponent(
            name=node.name,
            parent_components=[current_component.name],  # TODO: Should this be the actual component?
            block_name=node.name
        )
        components.append(generated_component)
    current_component = current_component if generated_component is None else generated_component
    if isinstance(node, For):
        print(f"For: {node.target} in {node.iter}")
    if isinstance(node, Getattr):
        print(f"Getattr node: {node}")
        print_getattr(node, current_component)
    if isinstance(node, Name):
        print(f"Field: {node.name}")
        log.debug(current_component.fields)
        if node.name not in [field.name for field in current_component.fields]:
            current_component.fields.append(Field(name=node.name, type="str"))

    for child_node in node.iter_child_nodes():
        print_indorder(child_node, current_component)


def generate_new(environment: Environment, import_types: bool) -> str:
    # Context to be used to populate actual components.j2 template
    context = Context(
        components=[],
        import_types=import_types,
    )
    assert environment.loader is not None, "No environment loader provided"

    template_names = environment.list_templates()  # TODO: Update to allow filtering of returned files, since this can return even non-template files
    for template_name in template_names:
        log.info(f"Parsing template: {template_name}")
        template_source = environment.loader.get_source(environment, template_name)[0]
        template_ast = environment.parse(template_source)

        referenced_templates = meta.find_referenced_templates(template_ast)

        current_component = GeneratedComponent(
            name=template_name,
            block_name="",
            parent_components=[template for template in referenced_templates if template is not None],
        )
        log.debug(current_component)
        components.append(current_component)

        print_indorder(template_ast, current_component)
    
    for c in components:
        print(c)
    return ""


def generate():
    templates_location = Path(config.templates_location)
    if not templates_location.is_dir():
        raise Exception(f"{config.templates_location} must be a directory")

    environment = Environment(loader=FileSystemLoader(templates_location))
    # output = _generate(environment, config.require_component_types)
    output = generate_new(environment, config.require_component_types)
    with open("components_gen.py", "w") as f:
        len_written = f.write(output)
        assert len_written == len(output)


if __name__ == "__main__":
    generate()
