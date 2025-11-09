from collections.abc import Iterable, Iterator
from dataclasses import dataclass, asdict
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, meta
from jinja2.nodes import Block, For, Name, Tuple

from volt import config

log = logging.getLogger("volt.generator.py")


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
    parent_fields: list[str] = []
    for parent_block in blocks:
        parent_fields.extend(get_block_fields(parent_block))

    fields = [field for field in get_block_fields(block) if field not in parent_fields]

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


def get_block_fields(block: Block) -> list[str]:
    fields: list[str] = []
    for block_body_node in block.body:
        excludes: list[Name] = []
        # TODO: Vars used in a for loop must be iterable
        # Can we also check if the target has fields, and use those as well?
        # block.
        fors = block.find_all(For)
        for f in fors:
            # Regular For loop, e.g. for item in items -> item is the target
            if isinstance(f.target, Name):
                excludes.append(f.target)
            # Occurs when unpacking as part of a for loop, e.g. for key, value in dict.items() -> (key, value) is the target
            elif isinstance(f.target, Tuple):
                for target in f.target.items:
                    assert isinstance(target, Name)
                    excludes.append(target)
            else:
                raise Exception(f"Unexpected For type: {type(f.target)} for {f.target}")

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

        referenced_templates = meta.find_referenced_templates(template_ast)

        template_blocks: list[Block] = []
        parent_components: list[str] = []
        blocks = template_ast.iter_child_nodes()
        for block in blocks:
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


def generate():
    templates_location = Path(config.templates_location)
    if not templates_location.is_dir():
        raise Exception(f"{config.templates_location} must be a directory")

    environment = Environment(loader=FileSystemLoader(templates_location))
    output = _generate(environment, config.require_component_types)
    with open("components_gen.py", "w") as f:
        len_written = f.write(output)
        assert len_written == len(output)


if __name__ == "__main__":
    generate()
