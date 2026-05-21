import os

def should_exclude(path, name):
    # Exclude directories
    exclude_dirs = {
        '.git', '.venv', '__pycache__', '.idea', 'data', 'node_modules'
    }
    # Exclude extensions
    exclude_exts = {
        '.db', '.sqlite', '.sqlite3', '.log', '.pyc', '.pyd', '.pyo', '.png', '.jpg', '.jpeg', '.webp', '.zip', '.tar', '.gz'
    }
    # Exclude specific files
    exclude_files = {
        'codebase_export.txt', 'database.sqlite', 'finance.db', 'finance_bot.db'
    }

    # Check if any parent folder is in exclude_dirs
    parts = path.split(os.sep)
    if any(d in exclude_dirs for d in parts):
        return True

    if name in exclude_files:
        return True

    if name.startswith('.env') and name != '.env.example':
        return True

    _, ext = os.path.splitext(name)
    if ext.lower() in exclude_exts:
        return True

    return False

def export_project(root_dir, output_file):
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write(f"=== PROJECT EXPORT: {os.path.basename(root_dir)} ===\n\n")
        
        # Write directory tree
        outfile.write("=== DIRECTORY STRUCTURE ===\n")
        for root, dirs, files in os.walk(root_dir):
            # Prune directory search
            dirs[:] = [d for d in dirs if d not in {'.git', '.venv', '__pycache__', '.idea', 'data', 'node_modules'}]
            
            level = root.replace(root_dir, '').count(os.sep)
            indent = ' ' * 4 * level
            outfile.write(f"{indent}{os.path.basename(root)}/\n")
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), root_dir)
                if not should_exclude(rel_path, f):
                    outfile.write(f"{subindent}{f}\n")
        
        outfile.write("\n" + "="*80 + "\n\n")

        # Write file contents
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in {'.git', '.venv', '__pycache__', '.idea', 'data', 'node_modules'}]
            
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, root_dir)
                
                if should_exclude(rel_path, f):
                    continue
                
                outfile.write("="*80 + "\n")
                outfile.write(f"FILE: {rel_path}\n")
                outfile.write("="*80 + "\n")
                
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='replace') as infile:
                        content = infile.read()
                    outfile.write(content)
                except Exception as e:
                    outfile.write(f"[ERROR READING FILE: {e}]")
                
                outfile.write("\n\n")

if __name__ == "__main__":
    project_root = r"c:\FinanceBot"
    output_path = os.path.join(project_root, "codebase_export.txt")
    print(f"Exporting codebase to {output_path}...")
    export_project(project_root, output_path)
    print("Done!")
