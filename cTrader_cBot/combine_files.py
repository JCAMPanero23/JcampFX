#!/usr/bin/env python3
"""
Combine all cBot files into single file for cTrader.
Removes duplicate using statements and namespace wrappers.
"""

from pathlib import Path


def extract_code_without_namespace(content):
    """Extract code inside namespace, removing the namespace wrapper."""
    lines = content.split('\n')
    result = []
    in_namespace = False
    namespace_depth = 0
    skip_next_brace = False

    for line in lines:
        # Skip using statements (we'll collect them separately)
        if line.strip().startswith('using '):
            continue

        # Detect namespace start
        if 'namespace JcampFX' in line:
            in_namespace = True
            skip_next_brace = True  # Skip the opening brace after namespace
            continue

        # Skip the opening brace immediately after namespace declaration
        if skip_next_brace and line.strip() == '{':
            skip_next_brace = False
            namespace_depth = 1  # We're now inside namespace
            continue

        # Track braces inside namespace
        if in_namespace:
            open_braces = line.count('{')
            close_braces = line.count('}')

            namespace_depth += open_braces
            namespace_depth -= close_braces

            # If we're at depth 0, namespace ended (closing brace)
            if namespace_depth <= 0 and close_braces > 0:
                in_namespace = False
                namespace_depth = 0
                continue

            # If we're inside namespace, collect the code
            if namespace_depth > 0:
                result.append(line)
        elif not in_namespace and line.strip() and not skip_next_brace:
            # Code outside namespace (shouldn't happen, but include it)
            result.append(line)

    return '\n'.join(result)


def extract_using_statements(content):
    """Extract all using statements."""
    lines = content.split('\n')
    usings = set()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('using ') and ';' in stripped:
            usings.add(stripped)

    return sorted(usings)


def combine_files():
    """Combine all 3 cBot files into single file."""
    files = [
        'MessageTypes.cs',
        'ZMQBridge.cs',
        'JcampFX_Brain.cs',
    ]

    all_usings = set()
    all_code = []

    print("Combining cBot files...")
    print("=" * 60)

    for filename in files:
        filepath = Path(filename)
        if not filepath.exists():
            print(f"[ERROR] File not found: {filename}")
            continue

        print(f"[OK] Processing: {filename}")
        content = filepath.read_text(encoding='utf-8')

        # Extract using statements
        usings = extract_using_statements(content)
        all_usings.update(usings)

        # Extract code without namespace wrapper
        code = extract_code_without_namespace(content)
        all_code.append(f"// ============================================================")
        all_code.append(f"// From: {filename}")
        all_code.append(f"// ============================================================")
        all_code.append(code)
        all_code.append("")

    # Build final combined file
    output_lines = []

    # Add using statements
    output_lines.extend(sorted(all_usings))
    output_lines.append("")

    # Add namespace wrapper
    output_lines.append("namespace JcampFX")
    output_lines.append("{")

    # Add all code (indented)
    for line in '\n'.join(all_code).split('\n'):
        if line.strip():
            output_lines.append("    " + line)
        else:
            output_lines.append("")

    # Close namespace
    output_lines.append("}")

    # Write output
    output_path = Path("JcampFX_Brain_COMBINED.cs")
    output_path.write_text('\n'.join(output_lines), encoding='utf-8')

    print("=" * 60)
    print(f"[SUCCESS] Combined file created: {output_path}")
    print(f"   Lines: {len(output_lines)}")
    print(f"   Size: {output_path.stat().st_size} bytes")
    print()
    print("Next steps:")
    print("1. Open cTrader -> Automate -> New cBot")
    print("2. Name it: JcampFX_Brain")
    print("3. Select ALL default code (Ctrl+A) and DELETE")
    print("4. Open JcampFX_Brain_COMBINED.cs in Notepad")
    print("5. Copy ALL (Ctrl+A, Ctrl+C)")
    print("6. Paste into cTrader editor (Ctrl+V)")
    print("7. Click Build (Ctrl+B)")
    print()


if __name__ == "__main__":
    combine_files()
    input("Press Enter to exit...")
