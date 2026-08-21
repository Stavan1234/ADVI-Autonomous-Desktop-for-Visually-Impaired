import json
import os
import sys

# Add src to sys.path so imports work
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from src.brain import Brain

def test():
    print("Testing read_file tool...")
    b = Brain()
    
    # 1. Create a txt file
    test_txt = os.path.abspath("test_file.txt")
    with open(test_txt, "w", encoding="utf-8") as f:
        f.write("This is a secret test file for phase 1.")
    
    # 2. Test reading it via tool
    result = b._execute_tool("read_file", {"path": test_txt, "question": "What is this?"})
    print(f"Result (TXT): {result}")
    
    res_json = json.loads(result)
    assert res_json.get("success") == True, "Failed to read txt file"
    assert "secret test file" in res_json.get("content", ""), "Content mismatch"
    
    # 3. Test reading docx file
    import docx
    doc = docx.Document()
    doc.add_paragraph("Word document content.")
    test_docx = os.path.abspath("test_document.docx")
    doc.save(test_docx)
    
    result2 = b._execute_tool("read_file", {"path": test_docx, "question": ""})
    print(f"Result (DOCX): {result2}")
    res_json2 = json.loads(result2)
    assert res_json2.get("success") == True, "Failed to read docx file"
    assert "Word document content." in res_json2.get("content", ""), "Content mismatch"

    print("Phase 1 test passed successfully!")
    
    # Cleanup
    if os.path.exists(test_txt): os.remove(test_txt)
    if os.path.exists(test_docx): os.remove(test_docx)

if __name__ == "__main__":
    test()
