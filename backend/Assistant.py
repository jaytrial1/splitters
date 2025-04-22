import google.generativeai as genai
import markdown
import re
import subprocess
import os
import pypandoc

# ------------ CONFIG ----------------
GEMINI_API_KEY = "AIzaSyC3ytLD5xZlCa70pkYajN2RjW4ehdoX6IU"
# ------------------------------------

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

def read_markdown_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

def extract_text_from_markdown(md_content):
    html_content = markdown.markdown(md_content)
    return re.sub(r"<[^>]*>", "", html_content)

def generate_prompt(question_types, include_answers):
    """Generate a dynamic prompt based on user selections"""
    
    # Map frontend values to human-readable names
    question_type_names = {
        'mcq': 'multiple-choice questions',
        'fib': 'fill in the blanks',
        'tf': 'true/false questions',
        'short': 'short answer questions',
        'long': 'long answer questions'
    }
    
    # Convert selected question types to readable format
    selected_types = [question_type_names.get(qt, qt) for qt in question_types]
    
    # Build the prompt
    prompt = (
        "I want you to read through the whole markdown file and generate a worksheet with "
        f"the following question types only: {', '.join(selected_types)}. "
        "The worksheet should be suitable for students to practice the content. "
    )
    
    # Add instruction about answers
    if include_answers:
        prompt += "At the end of the worksheet, include a section for correct answers. "
    else:
        prompt += "Do NOT include any answers in the worksheet. "
    
    prompt += (
        "Ensure every important topic is covered. "
        "Do not give anything else in your reply other than the worksheet.\n\n"
    )
    
    return prompt

def generate_worksheet(text, question_types, include_answers, print_fn=print):
    """Generate a worksheet based on the text and user preferences"""
    prompt = generate_prompt(question_types, include_answers)
    print_fn(f"Generating worksheet with prompt: {prompt[:100]}...")
    
    try:
        response = model.generate_content(prompt + text)
        return response.text.strip()
    except Exception as e:
        print_fn(f"Error generating worksheet with Gemini API: {str(e)}")
        # Fallback message if API fails
        return f"# Error Generating Worksheet\n\nThere was an error using the Gemini API: {str(e)}\n\nPlease try again later."

def save_as_markdown(content, filename, print_fn=print):
    """Save content to a markdown file"""
    with open(filename, "w", encoding="utf-8") as file:
        file.write(content)
    print_fn(f"✅ Saved as Markdown: {filename}")
    return filename

def convert_md_to_pdf(input_md, output_pdf, print_fn=print):
    """Convert markdown to PDF using pypandoc"""
    try:
        print_fn(f"Converting {input_md} to PDF...")
        # Use pypandoc instead of subprocess
        output = pypandoc.convert_file(
            input_md, 
            'pdf', 
            outputfile=output_pdf,
            extra_args=[
                '--pdf-engine=xelatex',
                '-V', 'geometry:margin=1in'
            ]
        )
        print_fn(f"✅ Converted to PDF: {output_pdf}")
        return output_pdf
    except Exception as e:
        print_fn(f"❌ PDF conversion failed: {str(e)}")
        try:
            # Fallback to simpler conversion
            print_fn("Trying alternative PDF conversion method...")
            output = pypandoc.convert_file(input_md, 'pdf', outputfile=output_pdf)
            print_fn(f"✅ Converted to PDF with alternative method: {output_pdf}")
            return output_pdf
        except Exception as e2:
            print_fn(f"❌ Alternative PDF conversion also failed: {str(e2)}")
            return None

def convert_md_to_docx(input_md, output_docx, print_fn=print):
    """Convert markdown to DOCX using pypandoc"""
    try:
        print_fn(f"Converting {input_md} to DOCX...")
        # Use pypandoc instead of subprocess
        output = pypandoc.convert_file(input_md, 'docx', outputfile=output_docx)
        print_fn(f"✅ Converted to DOCX: {output_docx}")
        return output_docx
    except Exception as e:
        print_fn(f"❌ DOCX conversion failed: {str(e)}")
        return None

def generate_worksheet_from_file(input_file, output_file=None, question_types=None, include_answers=True, output_format="md", print_fn=print):
    """Main function to generate a worksheet from a file"""
    try:
        if question_types is None:
            question_types = ["mcq", "fib", "tf", "short", "long"]
            
        print_fn(f"Reading input file: {input_file}")
        md_content = read_markdown_file(input_file)
        extracted_text = extract_text_from_markdown(md_content)
        
        print_fn("🤖 Generating worksheet using Gemini...")
        worksheet_md = generate_worksheet(extracted_text, question_types, include_answers, print_fn)
        
        # Create output path if not provided
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            output_file = f"{base_name}_worksheet"
        
        # Remove extension if present
        output_base = output_file.rsplit('.', 1)[0] if '.' in output_file else output_file
        
        # Save as markdown first
        md_output = save_as_markdown(worksheet_md, f"{output_base}.md", print_fn)
        
        # Convert to requested format if needed
        if output_format.lower() == "pdf":
            return convert_md_to_pdf(md_output, f"{output_base}.pdf", print_fn)
        elif output_format.lower() == "docx":
            return convert_md_to_docx(md_output, f"{output_base}.docx", print_fn)
        else:
            return md_output  # Return markdown file path
            
    except Exception as e:
        print_fn(f"❌ Error generating worksheet: {str(e)}")
        return None

# If run directly, use command line arguments
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate a worksheet from a markdown file")
    parser.add_argument("input_file", help="Path to the input markdown file")
    parser.add_argument("--output", "-o", help="Output file path (optional)")
    parser.add_argument("--format", "-f", choices=["md", "pdf", "docx"], default="md", 
                      help="Output format (md, pdf, docx)")
    parser.add_argument("--question-types", "-q", nargs="+", 
                      choices=["mcq", "fib", "tf", "short", "long"],
                      default=["mcq", "fib", "tf", "short", "long"],
                      help="Question types to include")
    parser.add_argument("--no-answers", action="store_true", 
                      help="Exclude answers from the worksheet")
    
    args = parser.parse_args()
    
    generate_worksheet_from_file(
        args.input_file,
        args.output,
        args.question_types,
        not args.no_answers,
        args.format
    )
