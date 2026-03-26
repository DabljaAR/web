#!/bin/bash
# Check for variable shadowing issues in Python code
# This script identifies imports that are duplicated at module and function level

echo "=== Checking for Variable Shadowing Issues ==="
echo

found_issues=0

# Function to check a file for shadowing
check_file() {
    local file="$1"
    
    # Get module-level imports (before first function/class definition)
    module_imports=$(awk '/^(def |class |@)/ {exit} /^import |^from .* import/ {print}' "$file" | \
                    sed 's/^import //; s/^from .* import //; s/ as .*//; s/,.*//; s/ .*//; s/\..*//g' | \
                    sort -u)
    
    # Check for duplicate imports inside functions
    for module in $module_imports; do
        # Look for imports of the same module inside functions/methods
        matches=$(grep -n "import $module\|from $module import" "$file" | \
                 awk -v mod="$module" '{
                     # Check if this line is inside a function/class (indented)
                     if ($0 ~ /^[0-9]+:[ \t]+/) {
                         print
                     }
                 }')
        
        if [ -n "$matches" ]; then
            echo "⚠️  Potential shadowing in $file:"
            echo "   Module '$module' imported at top level AND inside function:"
            echo "$matches" | sed 's/^/      /'
            echo
            found_issues=$((found_issues + 1))
        fi
    done
}

# Check all Python files in the project
echo "Scanning Python files..."
echo

# Check key files that had issues
for file in app/tts/models.py app/jobs/tasks/pipeline.py app/stt/models.py; do
    if [ -f "$file" ]; then
        check_file "$file"
    fi
done

echo "=== Scan Complete ==="
echo

if [ $found_issues -eq 0 ]; then
    echo "✅ No shadowing issues detected"
    exit 0
else
    echo "⚠️  Found $found_issues potential shadowing issue(s)"
    echo
    echo "Fix: Remove duplicate imports from inside functions."
    echo "Use the module-level import instead."
    exit 1
fi
