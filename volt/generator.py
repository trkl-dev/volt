from collections.abc import Iterable, Iterator
from dataclasses import dataclass, asdict
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, meta
from jinja2.nodes import Block, For, Name

log = logging.getLogger('volt.generator.py')

environment = Environment(loader=FileSystemLoader("templates/"))


@dataclass
class GeneratedComponent:
    name: str
    template_name: str
    block_name: str
    parent_components: Iterable[str]
    fields: list[str]


@dataclass
class Context:
    components: list[GeneratedComponent]
    import_types: bool


all_components: list[GeneratedComponent] = []


def get_block_children(block: Block, template_name: str, referenced_templates: Iterator[str | None], top_level: bool) -> Iterable[Block]:
    blocks: list[Block] = []

    child_blocks = block.iter_child_nodes()
    for child_block in child_blocks:
        if not isinstance(child_block, Block):
            continue
        log.debug(f"Inspecting block: {child_block.name}")
        blocks.append(child_block)
        blocks.extend(get_block_children(child_block, template_name, referenced_templates, top_level=False))

    # Set the name to just be the name of the block, unless the block is a content block,
    # in which case we name it the file name
    formatted_template_name = template_name[: template_name.find(".")].title()
    name = formatted_template_name + name_as_title(block.name)
    # if block.name == "content":
    #     name = template_name[: template_name.find(".")].title()

    fields = get_block_fields(block)

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


def get_block_fields(block: Block) -> list[str]:
    fields: list[str] = []
    for block_body_node in block.body:
        excludes: list[Name] = []
        # TODO: Vars used in a for loop must be iterable
        # Can we also check if the target has fields, and use those as well?
        # block.
        fors = block.find_all(For)
        for f in fors:
            assert isinstance(f.target, Name), (
                f"Unexpected For type: {type(f.target)} for {f.target}"
            )
            excludes.append(f.target)

        # TODO: Look at the `For` type and see if vars that are created from for loops can be omitted
        names = block_body_node.find_all(Name)
        for name in names:
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
                    if name.name == var:
                        already_exists = True
                if not already_exists:
                    fields.append(name.name)

    return fields

# TODO: Check against templates without blocks
# TODO: Figure out how to add Navbar to base.html component (top level blocks are not handled correctly atm)
def generate():
    context = Context(
        components=[],
        import_types=True,
    )

    if environment.loader is None:
        raise Exception("No environment loader")

    template_names = environment.list_templates()
    for template_name in template_names:
        log.info(f"Parsing template: {template_name}")
        template_source = environment.loader.get_source(environment, template_name)[0]
        template_ast = environment.parse(template_source)

        referenced_templates = meta.find_referenced_templates(template_ast)

        template_blocks: list[Block] = []
        parent_components: list[str] = []
        blocks = template_ast.iter_child_nodes()
        for block in blocks:
            if not isinstance(block, Block):
                continue
            log.debug(f"Inspecting block: {block.name}")
            template_blocks.extend(get_block_children(block, template_name, referenced_templates, top_level=True))
            parent_components.append(template_name[: template_name.find(".")].title() + name_as_title(block.name))

        name = template_name[: template_name.find(".")].title()
        all_components.append(GeneratedComponent(
            name=name,
            template_name=template_name,
            block_name="content",
            parent_components=parent_components,
            fields=[],
        ))


    for component in all_components:
        log.warning(f"component created: {component}")
        context.components.append(component)

    parent_dir = Path(__file__).parent
    gen_environment = Environment(loader=FileSystemLoader(parent_dir))
    template_file =  "components.py.j2"
    template = gen_environment.get_template(template_file)
    output = template.render(asdict(context))

    with open("components_gen.py", "w") as f:
        len_written = f.write(output)
        assert len_written == len(output)

if __name__ == "__main__":
    generate()
