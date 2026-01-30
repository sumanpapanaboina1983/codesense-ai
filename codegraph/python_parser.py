# python_parser.py
import ast
import json
import sys
import os
import re

# --- Docstring Parsing Utilities ---

def get_docstring_and_format(node):
    """
    Extracts the docstring from a node and determines its format.
    Returns (docstring, format) tuple.
    """
    docstring = ast.get_docstring(node)
    if not docstring:
        return None, None

    # Determine format based on content patterns
    format_type = detect_docstring_format(docstring)
    return docstring, format_type


def detect_docstring_format(docstring):
    """
    Detects the docstring format (Google, NumPy, reST, or unknown).
    """
    # Google style: uses indented sections like "Args:", "Returns:", "Raises:"
    google_patterns = [
        r'^\s*Args:\s*$',
        r'^\s*Returns:\s*$',
        r'^\s*Raises:\s*$',
        r'^\s*Yields:\s*$',
        r'^\s*Examples?:\s*$',
        r'^\s*Attributes:\s*$',
    ]

    # NumPy style: uses underlined sections like "Parameters", "Returns"
    numpy_patterns = [
        r'^\s*Parameters\s*\n\s*[-]+',
        r'^\s*Returns\s*\n\s*[-]+',
        r'^\s*Raises\s*\n\s*[-]+',
        r'^\s*Examples\s*\n\s*[-]+',
    ]

    # reST/Sphinx style: uses :param:, :returns:, :raises: directives
    rest_patterns = [
        r':param\s+\w+:',
        r':type\s+\w+:',
        r':returns?:',
        r':rtype:',
        r':raises?\s+\w+:',
    ]

    # Check for each format
    for pattern in numpy_patterns:
        if re.search(pattern, docstring, re.MULTILINE):
            return 'numpy'

    for pattern in rest_patterns:
        if re.search(pattern, docstring, re.IGNORECASE):
            return 'rest'

    for pattern in google_patterns:
        if re.search(pattern, docstring, re.MULTILINE):
            return 'google'

    return 'unknown'


def parse_docstring_tags(docstring, format_type):
    """
    Parses docstring into structured tags based on the detected format.
    Returns a list of DocTag-compatible dictionaries.
    """
    if not docstring:
        return []

    if format_type == 'google':
        return parse_google_docstring(docstring)
    elif format_type == 'numpy':
        return parse_numpy_docstring(docstring)
    elif format_type == 'rest':
        return parse_rest_docstring(docstring)
    else:
        return []


def parse_google_docstring(docstring):
    """
    Parses Google-style docstrings.
    """
    tags = []
    lines = docstring.split('\n')
    current_section = None
    current_content = []

    section_patterns = {
        'Args': 'param',
        'Arguments': 'param',
        'Parameters': 'param',
        'Returns': 'returns',
        'Return': 'returns',
        'Yields': 'yields',
        'Yield': 'yields',
        'Raises': 'throws',
        'Raise': 'throws',
        'Attributes': 'attribute',
        'Example': 'example',
        'Examples': 'example',
        'Note': 'note',
        'Notes': 'note',
        'Warning': 'warning',
        'Warnings': 'warning',
        'See Also': 'see',
        'Todo': 'todo',
        'Deprecated': 'deprecated',
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check for section header
        section_match = re.match(r'^(\w+(?:\s+\w+)?)\s*:\s*$', stripped)
        if section_match:
            section_name = section_match.group(1)
            if section_name in section_patterns:
                current_section = section_patterns[section_name]
                i += 1
                continue

        # Parse content within sections
        if current_section == 'param':
            # Format: name (type): description or name: description
            param_match = re.match(r'^\s{2,}(\w+)\s*(?:\(([^)]+)\))?\s*:\s*(.*)$', line)
            if param_match:
                tags.append({
                    'tag': 'param',
                    'name': param_match.group(1),
                    'type': param_match.group(2),
                    'description': param_match.group(3).strip() or None,
                })

        elif current_section in ('returns', 'yields'):
            # Format: type: description or just description
            return_match = re.match(r'^\s{2,}(?:(\w+(?:\[.*?\])?)\s*:\s*)?(.*)$', line)
            if return_match and (return_match.group(1) or return_match.group(2)):
                tags.append({
                    'tag': current_section,
                    'type': return_match.group(1),
                    'description': return_match.group(2).strip() or None,
                })

        elif current_section == 'throws':
            # Format: ExceptionType: description
            raise_match = re.match(r'^\s{2,}(\w+)\s*:\s*(.*)$', line)
            if raise_match:
                tags.append({
                    'tag': 'throws',
                    'type': raise_match.group(1),
                    'description': raise_match.group(2).strip() or None,
                })

        elif current_section == 'deprecated':
            if stripped:
                tags.append({
                    'tag': 'deprecated',
                    'description': stripped,
                })

        elif current_section == 'example':
            # Collect example content
            if stripped:
                existing = next((t for t in tags if t['tag'] == 'example'), None)
                if existing:
                    existing['description'] = (existing.get('description', '') + '\n' + line).strip()
                else:
                    tags.append({
                        'tag': 'example',
                        'description': stripped,
                    })

        i += 1

    return tags


def parse_numpy_docstring(docstring):
    """
    Parses NumPy-style docstrings.
    """
    tags = []
    lines = docstring.split('\n')

    section_map = {
        'Parameters': 'param',
        'Returns': 'returns',
        'Yields': 'yields',
        'Raises': 'throws',
        'Attributes': 'attribute',
        'Examples': 'example',
        'Notes': 'note',
        'Warnings': 'warning',
        'See Also': 'see',
        'Deprecated': 'deprecated',
    }

    current_section = None
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check for section header (followed by underline)
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and all(c == '-' for c in next_line):
                if stripped in section_map:
                    current_section = section_map[stripped]
                    i += 2  # Skip header and underline
                    continue

        # Parse content within sections
        if current_section == 'param':
            # Format: name : type\n    description
            param_match = re.match(r'^(\w+)\s*:\s*(.*)$', stripped)
            if param_match:
                param_name = param_match.group(1)
                param_type = param_match.group(2) or None

                # Collect description from following indented lines
                description_lines = []
                i += 1
                while i < len(lines) and (lines[i].startswith('    ') or lines[i].strip() == ''):
                    if lines[i].strip():
                        description_lines.append(lines[i].strip())
                    i += 1

                tags.append({
                    'tag': 'param',
                    'name': param_name,
                    'type': param_type.strip() if param_type else None,
                    'description': ' '.join(description_lines) if description_lines else None,
                })
                continue

        elif current_section in ('returns', 'yields'):
            # Format: type\n    description
            if stripped and not stripped.startswith(' '):
                return_type = stripped
                description_lines = []
                i += 1
                while i < len(lines) and (lines[i].startswith('    ') or lines[i].strip() == ''):
                    if lines[i].strip():
                        description_lines.append(lines[i].strip())
                    i += 1

                tags.append({
                    'tag': current_section,
                    'type': return_type,
                    'description': ' '.join(description_lines) if description_lines else None,
                })
                continue

        elif current_section == 'throws':
            # Format: ExceptionType\n    description
            if stripped and not stripped.startswith(' '):
                exception_type = stripped
                description_lines = []
                i += 1
                while i < len(lines) and (lines[i].startswith('    ') or lines[i].strip() == ''):
                    if lines[i].strip():
                        description_lines.append(lines[i].strip())
                    i += 1

                tags.append({
                    'tag': 'throws',
                    'type': exception_type,
                    'description': ' '.join(description_lines) if description_lines else None,
                })
                continue

        i += 1

    return tags


def parse_rest_docstring(docstring):
    """
    Parses reStructuredText/Sphinx-style docstrings.
    """
    tags = []

    # :param name: description
    for match in re.finditer(r':param\s+(\w+):\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        tags.append({
            'tag': 'param',
            'name': match.group(1),
            'description': ' '.join(match.group(2).split()),
        })

    # :type name: type
    for match in re.finditer(r':type\s+(\w+):\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        # Find existing param and add type
        param_name = match.group(1)
        param_type = ' '.join(match.group(2).split())
        for tag in tags:
            if tag['tag'] == 'param' and tag['name'] == param_name:
                tag['type'] = param_type
                break

    # :returns: or :return: description
    for match in re.finditer(r':returns?:\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        tags.append({
            'tag': 'returns',
            'description': ' '.join(match.group(1).split()),
        })

    # :rtype: type
    for match in re.finditer(r':rtype:\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        # Find existing returns and add type
        return_type = ' '.join(match.group(1).split())
        for tag in tags:
            if tag['tag'] == 'returns':
                tag['type'] = return_type
                break
        else:
            # No returns tag found, create one with just type
            tags.append({
                'tag': 'returns',
                'type': return_type,
            })

    # :raises ExceptionType: description
    for match in re.finditer(r':raises?\s+(\w+):\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        tags.append({
            'tag': 'throws',
            'type': match.group(1),
            'description': ' '.join(match.group(2).split()),
        })

    # :deprecated: description
    for match in re.finditer(r':deprecated:\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        tags.append({
            'tag': 'deprecated',
            'description': ' '.join(match.group(1).split()),
        })

    # :example: or .. code-block::
    for match in re.finditer(r':example:\s*(.+?)(?=\n\s*:|$)', docstring, re.DOTALL):
        tags.append({
            'tag': 'example',
            'description': match.group(1).strip(),
        })

    return tags


def extract_summary(docstring):
    """
    Extracts the summary (first paragraph) from a docstring.
    """
    if not docstring:
        return None

    lines = docstring.strip().split('\n')
    summary_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            break
        # Stop at section headers (Google/NumPy style)
        if re.match(r'^(\w+(?:\s+\w+)?)\s*:\s*$', stripped):
            break
        # Stop at reST directives
        if stripped.startswith(':') or stripped.startswith('..'):
            break
        summary_lines.append(stripped)

    return ' '.join(summary_lines) if summary_lines else None


def build_documentation_info(node):
    """
    Builds a complete documentation info dictionary for a node.
    """
    docstring, format_type = get_docstring_and_format(node)

    if not docstring:
        return None

    tags = parse_docstring_tags(docstring, format_type)
    summary = extract_summary(docstring)

    # Extract specific metadata from tags
    is_deprecated = any(t['tag'] == 'deprecated' for t in tags)
    deprecation_reason = next((t.get('description') for t in tags if t['tag'] == 'deprecated'), None)
    examples = [t.get('description') for t in tags if t['tag'] == 'example' and t.get('description')]
    see_also = [t.get('description') for t in tags if t['tag'] == 'see' and t.get('description')]

    return {
        'summary': summary,
        'rawComment': docstring,
        'tags': tags,
        'format': 'docstring',
        'isDeprecated': is_deprecated if is_deprecated else None,
        'deprecationReason': deprecation_reason,
        'examples': examples if examples else None,
        'seeAlso': see_also if see_also else None,
    }


# --- Node Visitor ---
class PythonAstVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        # Normalize path immediately in constructor for consistency
        self.filepath = filepath.replace('\\', '/')
        self.nodes = []
        self.relationships = []
        self.current_class_name = None
        self.current_class_entity_id = None
        self.current_func_entity_id = None # Can be function or method
        self.module_entity_id = None # Store the module/file entity id

    def _get_location(self, node):
        # ast line numbers are 1-based, columns are 0-based
        if isinstance(node, ast.Module):
            # Module node represents the whole file, return default location
            return {"startLine": 1, "endLine": 1, "startColumn": 0, "endColumn": 0}
        try:
            # Attempt to get standard location attributes
            return {
                "startLine": node.lineno,
                "endLine": getattr(node, 'end_lineno', node.lineno),
                "startColumn": node.col_offset,
                "endColumn": getattr(node, 'end_col_offset', -1)
            }
        except AttributeError:
            # Fallback for nodes that might unexpectedly lack location info
            # print(f"DEBUG: Node type {type(node).__name__} lacks location attributes.", file=sys.stderr) # Optional debug
            return {"startLine": 0, "endLine": 0, "startColumn": 0, "endColumn": 0}

    def _generate_entity_id(self, kind, qualified_name, line_number=None):
        # Simple entity ID generation - can be refined
        # Use lowercase kind for consistency
        # Include line number for kinds prone to name collision within the same file scope
        if kind.lower() in ['pythonvariable', 'pythonparameter'] and line_number is not None:
            unique_qualifier = f"{qualified_name}:{line_number}"
        else:
            unique_qualifier = qualified_name
        return f"{kind.lower()}:{self.filepath}:{unique_qualifier}" # Added closing brace

    def _add_node(self, kind, name, node, parent_id=None, extra_props=None, documentation_info=None):
         location = self._get_location(node)
         # Generate qualified name based on context (Original simpler logic)
         if kind == 'PythonMethod' and self.current_class_name:
             qualified_name = f"{self.current_class_name}.{name}"
         else:
             qualified_name = name

         # Pass line number to entity ID generation for relevant kinds
         entity_id = self._generate_entity_id(kind, qualified_name, location['startLine'])

         node_data = {
             "kind": kind,
             "name": name,
             "filePath": self.filepath, # Use normalized path from constructor
             "entityId": entity_id,
             **location,
             "language": "Python",
             "properties": extra_props or {}
         }
         if parent_id:
             node_data["parentId"] = parent_id

         # Add documentation info if available
         if documentation_info:
             node_data["documentation"] = documentation_info.get("summary")
             node_data["docComment"] = documentation_info.get("rawComment")
             node_data["documentationInfo"] = documentation_info
             if documentation_info.get("tags"):
                 node_data["tags"] = documentation_info["tags"]

         # Store module entity id when creating the File node
         if kind == 'File':
             self.module_entity_id = entity_id

         self.nodes.append(node_data)
         return entity_id # Return entityId for linking relationships

    def _add_relationship(self, type, source_id, target_id, extra_props=None):
         # Simple entity ID for relationships
         rel_entity_id = f"{type.lower()}:{source_id}:{target_id}"
         self.relationships.append({
             "type": type,
             "sourceId": source_id,
             "targetId": target_id,
             "entityId": rel_entity_id,
             "properties": extra_props or {}
         })

    def visit_FunctionDef(self, node):
        parent_id = None
        kind = 'PythonFunction' # Use specific kind
        if self.current_class_entity_id:
            kind = 'PythonMethod' # Use specific kind
            parent_id = self.current_class_entity_id

        # Extract documentation info
        doc_info = build_documentation_info(node)

        # Extract decorators
        decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    decorators.append(decorator.func.id)
                elif isinstance(decorator.func, ast.Attribute):
                    decorators.append(decorator.func.attr)

        # Extract return type annotation if present
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)

        # Build extra properties
        extra_props = {}
        if decorators:
            extra_props['decorators'] = decorators
        if return_type:
            extra_props['returnType'] = return_type
        if isinstance(node, ast.AsyncFunctionDef):
            extra_props['isAsync'] = True

        # Store current func/method ID for parameters
        original_parent_func_id = self.current_func_entity_id
        func_entity_id = self._add_node(
            kind, node.name, node,
            parent_id=parent_id,
            extra_props=extra_props if extra_props else None,
            documentation_info=doc_info
        )
        self.current_func_entity_id = func_entity_id

        # Add relationship from class to method
        if kind == 'PythonMethod' and self.current_class_entity_id:
            self._add_relationship('PYTHON_HAS_METHOD', self.current_class_entity_id, func_entity_id)
        # Add relationship from file/module to function
        elif kind == 'PythonFunction' and self.module_entity_id:
             self._add_relationship('PYTHON_DEFINES_FUNCTION', self.module_entity_id, func_entity_id)


        # Visit arguments (parameters)
        if node.args:
            for arg in node.args.args:
                param_entity_id = self._add_node('PythonParameter', arg.arg, arg, parent_id=func_entity_id)
                self._add_relationship('PYTHON_HAS_PARAMETER', func_entity_id, param_entity_id)
            # Handle *args, **kwargs if needed

        # Visit function body
        self.generic_visit(node)
        # Restore parent func ID
        self.current_func_entity_id = original_parent_func_id


    def visit_AsyncFunctionDef(self, node):
        # Treat async functions similarly to regular functions for now
        self.visit_FunctionDef(node) # Reuse logic, maybe add isAsync property

    def visit_ClassDef(self, node):
        original_class_name = self.current_class_name
        original_class_entity_id = self.current_class_entity_id

        # Extract documentation info
        doc_info = build_documentation_info(node)

        # Extract decorators
        decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    decorators.append(decorator.func.id)
                elif isinstance(decorator.func, ast.Attribute):
                    decorators.append(decorator.func.attr)

        # Extract base classes
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.unparse(base) if hasattr(ast, 'unparse') else base.attr)

        # Build extra properties
        extra_props = {}
        if decorators:
            extra_props['decorators'] = decorators
        if bases:
            extra_props['bases'] = bases

        self.current_class_name = node.name
        self.current_class_entity_id = self._add_node(
            'PythonClass', node.name, node,
            extra_props=extra_props if extra_props else None,
            documentation_info=doc_info
        )

        # Add relationship from file/module to class
        if self.module_entity_id:
             self._add_relationship('PYTHON_DEFINES_CLASS', self.module_entity_id, self.current_class_entity_id)

        # Visit class body (methods, nested classes, etc.)
        self.generic_visit(node)

        self.current_class_name = original_class_name
        self.current_class_entity_id = original_class_entity_id

    def visit_Import(self, node):
        for alias in node.names:
            # Simple import relationship (Module -> Module Name)
            # More complex resolution (finding the actual file) is deferred
            target_name = alias.name
            target_entity_id = self._generate_entity_id('pythonmodule', target_name) # Placeholder ID for module
            # Use the stored module/file entityId as source
            # Explicitly create the target module node (placeholder)
            self._add_node('PythonModule', target_name, node) # Use import node for location approximation
            if self.module_entity_id:
                self._add_relationship('PYTHON_IMPORTS', self.module_entity_id, target_entity_id, {"importedName": alias.asname or alias.name})

    def visit_ImportFrom(self, node):
        module_name = node.module or '.' # Handle relative imports
        # Placeholder ID for the imported module
        target_module_entity_id = self._generate_entity_id('pythonmodule', module_name)
        # Explicitly create the target module node (placeholder)
        self._add_node('PythonModule', module_name, node) # Use import node for location approximation
        # Use the stored module/file entityId as source
        if self.module_entity_id:
            imported_names = []
            for alias in node.names:
                imported_names.append(alias.asname or alias.name)
                # Could potentially create relationships for specific imported items later

            self._add_relationship('PYTHON_IMPORTS', self.module_entity_id, target_module_entity_id, {"importedNames": imported_names, "fromModule": module_name})

    def visit_Assign(self, node):
         # Basic variable assignment detection
         # More complex assignments (tuples, etc.) require more logic
         for target in node.targets:
             if isinstance(target, ast.Name):
                 # Determine parent scope (function, method, class, or module)
                 parent_scope_id = self.current_func_entity_id or self.current_class_entity_id or self.module_entity_id
                 if parent_scope_id: # Ensure parent scope exists
                    self._add_node('PythonVariable', target.id, node, parent_id=parent_scope_id)
         self.generic_visit(node) # Visit the value being assigned

    def visit_Call(self, node):
        # Basic call detection
        func_name = None
        if isinstance(node.func, ast.Name): # Direct function call like my_func()
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute): # Method call like obj.method() or Class.method()
            # Try to reconstruct the full call name (e.g., 'self.method', 'ClassName.static_method')
            # This is complex and requires symbol resolution beyond basic AST walking
            # For now, just use the attribute name
            func_name = node.func.attr

        # Capture calls from module level as well
        source_entity_id = self.current_func_entity_id or self.module_entity_id

        if func_name and source_entity_id:
            # Target ID is tricky without resolution - use a placeholder based on name
            # Use 'pythonfunction' as a placeholder kind instead of 'unknown'
            target_entity_id = self._generate_entity_id('pythonfunction', func_name)
            self._add_relationship('PYTHON_CALLS', source_entity_id, target_entity_id, {"calledName": func_name})

        self.generic_visit(node) # Visit arguments

# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "File path argument required."}), file=sys.stderr)
        sys.exit(1)

    filepath_arg = sys.argv[1]
    # Normalize the path within Python using os.path.abspath
    filepath = os.path.abspath(filepath_arg)
    # print(f"DEBUG: Received path: '{filepath_arg}', Absolute path: '{filepath}'", file=sys.stderr) # Keep debug if needed

    if not os.path.exists(filepath):
         print(json.dumps({"error": f"File not found (checked absolute path): {filepath}"}), file=sys.stderr)
         sys.exit(1)

    try:
        # Use the normalized, absolute path
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content, filename=filepath)

        # Pass the normalized, absolute path to the visitor
        visitor = PythonAstVisitor(filepath)

        # Extract module-level docstring
        module_doc_info = build_documentation_info(tree)

        # Add the File node itself using the correct kind, with module docstring if present
        visitor._add_node('File', os.path.basename(filepath), tree, documentation_info=module_doc_info)
        visitor.visit(tree)

        result = {
            "filePath": visitor.filepath, # Already normalized in visitor
            "nodes": visitor.nodes,
            "relationships": visitor.relationships
        }
        print(json.dumps(result, indent=2)) # Output JSON to stdout

    except Exception as e:
        # Use the normalized, absolute path in the error message
        print(json.dumps({"error": f"Error parsing {filepath}: {str(e)}"}), file=sys.stderr)
        sys.exit(1)