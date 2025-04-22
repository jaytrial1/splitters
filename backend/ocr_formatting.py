import os
import re
import time
from pathlib import Path

import google.generativeai as genai
from mistralai import Mistral, DocumentURLChunk
from mistralai.models import OCRResponse
from tqdm import tqdm


# === INIT GEMINI ===
def init_gemini():
    api_key = "AIzaSyC3ytLD5xZlCa70pkYajN2RjW4ehdoX6IU"  # Replace with your Gemini API key
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")


# === IMAGE REMOVAL (OCR Side) ===
def replace_images_in_markdown(markdown_str: str, images_dict: dict) -> str:
    # Skip embedding base64 image strings completely
    return markdown_str


# === OCR RESPONSE TO CLEAN MARKDOWN ===
def get_combined_markdown(ocr_response: OCRResponse) -> str:
    markdowns = []
    for page in ocr_response.pages:
        image_data = {img.id: img.image_base64 for img in page.images}
        markdowns.append(replace_images_in_markdown(page.markdown, image_data))
    return "\n\n".join(markdowns)


# === CLEAN INLINE BASE64 IMAGES (Fallback) ===
def remove_inline_images(markdown: str) -> str:
    return re.sub(r'!\[.*?\]\(data:image\/[a-zA-Z]+;base64,[^\)]*\)', '', markdown)


# === STRIP HEADER/SUBHEADER FORMATTING ===
def strip_headers(markdown: str) -> str:
    """
    Removes all header/subheader formatting from markdown while preserving the text.
    This includes:
    - # Header 1
    - ## Header 2
    - ### Header 3
    - etc.
    - Underlined headers (=== or ---)
    
    Args:
        markdown (str): The markdown text to process
        
    Returns:
        str: Markdown with headers converted to plain text
    """
    # Remove # headers
    markdown = re.sub(r'^#+\s+(.+)$', r'\1', markdown, flags=re.MULTILINE)
    
    # Remove underlined headers (=== or ---)
    markdown = re.sub(r'^(.+)\n[=-]+\n', r'\1\n', markdown, flags=re.MULTILINE)
    
    return markdown


# === GENERATE TABLE OF CONTENTS ===
def generate_toc(markdown: str, print_fn=print) -> str:
    """
    Uses Gemini to analyze the markdown and generate a structured Table of Contents.
    
    Args:
        markdown (str): The cleaned markdown text to analyze
        print_fn (function): Function to use for printing progress
        
    Returns:
        str: A markdown-formatted Table of Contents
    """
    model = init_gemini()
    
    prompt = (
        "You are an expert at analyzing documents and creating structured Table of Contents. "
        "Analyze the following markdown content and create a hierarchical Table of Contents. "
        "The Table of Contents should:\n"
        "1. Include all major sections (#)\n"
        "2. Include subsections (##) where appropriate\n"
        "3. Use proper markdown formatting with # symbols\n"
        "4. Maintain a logical hierarchy\n"
        "5. Be concise but descriptive\n"
        "Here's the content to analyze:\n\n"
        f"{markdown}"
    )
    
    try:
        print_fn("📑 Generating Table of Contents...")
        response = model.generate_content(prompt)
        toc = response.text
        
        # Ensure the ToC is properly formatted
        if not toc.strip().startswith("#"):
            toc = "# Table of Contents\n\n" + toc
            
        print_fn("✅ Table of Contents generated successfully")
        return toc
        
    except Exception as e:
        print_fn(f"❌ Failed to generate Table of Contents: {e}")
        return None


# === INITIAL PROCESSING ===
def process_initial_markdown(raw_markdown: str, print_fn=print) -> tuple[str, str]:
    """
    Processes the initial markdown by stripping headers and generating ToC.
    
    Args:
        raw_markdown (str): The raw markdown from OCR
        print_fn (function): Function to use for printing progress
        
    Returns:
        tuple[str, str]: A tuple containing (cleaned_markdown, table_of_contents)
    """
    print_fn("🧼 Stripping headers...")
    cleaned_markdown = strip_headers(raw_markdown)
    
    print_fn("📑 Generating Table of Contents...")
    toc = generate_toc(cleaned_markdown, print_fn)
    
    return cleaned_markdown, toc


# === PROCESS SECTIONS ===
def process_sections(markdown_with_breaks: str, output_folder: str = None, print_fn=print) -> dict:
    """
    Processes the markdown that has section breaks, sending each section to Gemini
    for formatting. Instead of merging, saves each section as a separate file.
    
    Args:
        markdown_with_breaks (str): Markdown with section breaks
        output_folder (str): Folder to save section files (created if doesn't exist)
        print_fn (function): Function to use for printing progress
        
    Returns:
        dict: Information about processed sections including file paths
    """
    model = init_gemini()
    section_break = "=====Section Break====="
    
    # Split the markdown into sections
    sections = markdown_with_breaks.split(section_break)
    processed_sections = []
    section_files = []
    
    # Create output folder if specified and doesn't exist
    if output_folder and not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)
        print_fn(f"📁 Created folder: {output_folder}")
    
    print_fn(f"📝 Processing {len(sections)} sections...")
    
    for i, section in enumerate(sections, 1):
        if not section.strip():
            continue
            
        # Extract section title from first line
        section_lines = section.strip().split('\n')
        section_title = section_lines[0].strip() if section_lines else f"Section_{i}"
        
        # Remove problematic characters from filename
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', section_title)
        if not safe_title:
            safe_title = f"Section_{i}"
            
        # Process section content
        print_fn(f"Processing section {i}: {section_title}...")
        prompt = (
            "You are an expert at editing and formatting Markdown documents. "
            "Your job is to organize this section professionally with proper hierarchical headers. "
            "IMPORTANT: The first line is the section title - DO NOT modify or format it in any way. "
            "Only format the content that follows the first line.\n\n"
            "Follow these specific formatting rules for the content after the first line:\n\n"
            "1. Main topics should use a single # (Header 1)\n"
            "2. First level subtopics should use ## (Header 2)\n"
            "3. Second level subtopics should use ### (Header 3)\n"
            "4. Third level subtopics should use #### (Header 4)\n"
            "5. Always maintain this hierarchy - never skip levels\n"
            "6. Preserve all original content and meaning\n"
            "7. Fix any grammatical errors\n"
            "8. Ensure proper spacing between sections\n"
            "9. Keep the formatting consistent throughout\n\n"
            "Here's the section to format (remember: first line is the title, do not modify it):\n\n"
            f"{section}"
        )
        
        try:
            response = model.generate_content(prompt)
            processed_content = response.text
            processed_sections.append({
                'title': section_title,
                'content': processed_content
            })
            
            # Save section to file if output folder is specified
            if output_folder:
                file_name = f"{safe_title}.md"
                file_path = os.path.join(output_folder, file_name)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(processed_content)
                
                section_files.append({
                    'title': section_title,
                    'file_name': file_name,
                    'file_path': file_path
                })
                
                print_fn(f"✅ Section {i} processed and saved as: {file_name}")
            else:
                print_fn(f"✅ Section {i} processed successfully")
                
        except Exception as e:
            print_fn(f"❌ Failed to process section {i}: {e}")
            # If processing fails, keep the original section
            processed_sections.append({
                'title': section_title,
                'content': section
            })
            
            if output_folder:
                file_name = f"{safe_title}_original.md"
                file_path = os.path.join(output_folder, file_name)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(section)
                
                section_files.append({
                    'title': section_title,
                    'file_name': file_name,
                    'file_path': file_path,
                    'error': str(e)
                })
                
                print_fn(f"⚠️ Section {i} saved as original content: {file_name}")
    
    result = {
        'processed_sections': processed_sections,
        'section_files': section_files
    }
    
    print_fn(f"✅ All {len(section_files)} sections processed and saved")
    
    return result


# === CLEAN & FORMAT MARKDOWN WITH GEMINI ===
def clean_and_format_markdown(raw_markdown: str, output_path: str, retries: int = 3, print_fn=print) -> str:
    model = init_gemini()
    
    try:
        print_fn("Processing markdown...")
        prompt = (
            "You are an expert at editing and formatting Markdown documents. "
            "Your job is to organize this section professionally, fix formatting, perform spell check and preserve **every word**. "
            "If you find the text to be gibberish then remove that part and add the relevant text according to your expertise. "
            "If you find any grammatical errors, fix them. "
            "If you find some text to be missing then add only the extremely necessary text according to the surrounding context."
            "Important : each subtopic of this section (if any) should have proper header and subheader using in proper order only(#, ##, ### etc.) "
            "Avoid summarizing. Here's the section:\n\n"
            f"{raw_markdown}"
        )
        
        response = model.generate_content(prompt)
        cleaned_markdown = response.text
        
        # Save the processed markdown
        with open(output_path, "w", encoding="utf-8") as final_file:
            final_file.write(cleaned_markdown)
        print_fn(f"\n✅ Cleaned markdown saved to: {output_path}")
        
        return cleaned_markdown
        
    except Exception as e:
        print_fn(f"❌ Failed to process markdown: {e}")
        return None


# === MAIN DRIVER ===
def main(pdf_path, output_path=None, print_fn=print):
    print_fn("Starting OCR process...")
    mistral_api_key = "NYXadtJ6Oh6CM3KQh8SuLnqYeCgxQcqq"  # Replace with your Mistral API key
    client = Mistral(api_key=mistral_api_key)

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        print_fn(f"❌ File {pdf_path} does not exist.")
        return None

    # Create default output path if not provided
    if output_path is None:
        output_path = f"{pdf_path.stem}_cleaned.md"

    # Upload to Mistral
    print_fn("📤 Uploading file to Mistral...")
    uploaded_file = client.files.upload(
        file={
            "file_name": pdf_path.stem,
            "content": pdf_path.read_bytes(),
        },
        purpose="ocr",
    )
    signed_url = client.files.get_signed_url(file_id=uploaded_file.id, expiry=1)

    # Run OCR
    print_fn("📄 Running OCR...")
    pdf_response = client.ocr.process(
        document=DocumentURLChunk(document_url=signed_url.url),
        model="mistral-ocr-latest",
        include_image_base64=True
    )

    # Combine OCR output to markdown
    print_fn("📝 Extracting text from OCR results...")
    raw_markdown = get_combined_markdown(pdf_response)
    print_fn("🧼 Removing inline base64 images...")
    raw_markdown = remove_inline_images(raw_markdown)
    
    # Process initial markdown (strip headers and generate ToC)
    print_fn("🧼 Initial markdown processing...")
    cleaned_markdown, toc = process_initial_markdown(raw_markdown, print_fn)
    
    # Save the initial markdown for user review
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned_markdown)
    
    print_fn(f"✅ Initial markdown saved to: {output_path}")
    print_fn("📝 The document is ready for adding section breaks")
    
    return output_path, toc


if __name__ == "__main__":
    main("12 CBSE\\EP\\18_Enterpreneurship_Book (2)-39-96.pdf")
