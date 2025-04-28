from flask import Flask, request, send_file, jsonify, Response
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import sys
import uuid
import threading
import time
import json
from pathlib import Path
import traceback
import shutil
import zipfile
import glob
import io
import requests
# Import the modules from the correct location
try:
    from backend.ocr_formatting import main as ocr_process, clean_and_format_markdown, process_initial_markdown, process_sections
    from backend.Assistant import generate_worksheet_from_file
except ImportError as e:
    print(f"Import error: {e}. Trying alternative import path...")
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from backend.ocr_formatting import main as ocr_process, clean_and_format_markdown, process_initial_markdown, process_sections
        from backend.Assistant import generate_worksheet_from_file
    except ImportError as e2:
        print(f"Alternative import also failed: {e2}")
        print(f"Current sys.path: {sys.path}")
        print(f"Current directory: {os.getcwd()}")
        raise

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes and origins

# Create directories with absolute paths
BASE_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
UPLOAD_DIR = BASE_DIR / "uploaded_files"
PROCESSED_DIR = BASE_DIR / "processed_docs"
STORAGE_DIR = BASE_DIR / "storage_folder"
UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(exist_ok=True)

print(f"Base directory: {BASE_DIR}")
print(f"Upload directory: {UPLOAD_DIR}")
print(f"Processed directory: {PROCESSED_DIR}")
print(f"Storage directory: {STORAGE_DIR}")

# Store processing status messages
processing_status = {}
# Add a mapping to track if a process ID is for a folder
process_type = {} # { process_id: 'file' | 'folder' }

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/process-pdf', methods=['POST'])
def process_pdf():
    try:
        print("Received /process-pdf request")
        
        if 'file' not in request.files:
            print("No file part in the request")
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        if file.filename == '':
            print("No file selected")
            return jsonify({'error': 'No file selected'}), 400
        
        print(f"File received: {file.filename}, Content-Type: {file.content_type}")
        
        # Get optional prompt    
        prompt = request.form.get('prompt', '')
        print(f"Prompt: {prompt[:50]}..." if len(prompt) > 50 else f"Prompt: {prompt}")
        
        # Generate unique ID for this process
        process_id = str(uuid.uuid4())
        processing_status[process_id] = []
        process_type[process_id] = 'file' # Mark as single file process
        
        # Save uploaded file with absolute path
        filename = secure_filename(file.filename)
        file_path = UPLOAD_DIR / filename
        file.save(str(file_path))
        print(f"Saved file to: {file_path}")
        
        # Add first status message
        processing_status[process_id].append("File uploaded successfully")
        
        # Start processing in a separate thread
        thread = threading.Thread(
            target=process_pdf_thread,
            args=(str(file_path), process_id, prompt)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing',
            'process_id': process_id
        })
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in process_pdf: {str(e)}", file=sys.stderr)
        print(f"Traceback: {error_traceback}", file=sys.stderr)
        return jsonify({'error': str(e), 'traceback': error_traceback}), 500

def process_pdf_thread(file_path, process_id, prompt):
    try:
        # Create a custom print function that captures output
        def custom_print(message):
            print(message)  # Still print to console
            processing_status[process_id].append(message)
        
        # Use the original OCR process but with our custom print
        output_path = PROCESSED_DIR / f"{process_id}_output.md"
        
        # Call OCR process with original functionality
        # The function now returns a tuple (output_path, toc)
        result = ocr_process(file_path, str(output_path), print_fn=custom_print)
        
        # Check if result is valid
        if result:
            output_path_str, toc = result
            
            # Read the processed content
            if os.path.exists(output_path):
                with open(output_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Add final status message
                processing_status[process_id].append("Initial processing complete!")
                processing_status[process_id].append("READY_FOR_SECTIONS:" + content)
                
                # Add the TOC if available
                if toc:
                    processing_status[process_id].append("TOC:" + toc)
                
                # Clean up temporary files
                os.remove(file_path)
            else:
                processing_status[process_id].append("ERROR: Processing failed - output file not found")
        else:
            processing_status[process_id].append("ERROR: OCR process failed")
            
    except Exception as e:
        error_message = f"Error processing PDF: {str(e)}"
        print(error_message, file=sys.stderr)
        processing_status[process_id].append(f"ERROR: {error_message}")

@app.route('/process-status/<process_id>', methods=['GET'])
def get_process_status(process_id):
    if process_id not in processing_status:
        print(f"Process ID not found: {process_id}")
        return jsonify({
            'error': 'Process ID not found',
            'message': 'The requested process ID does not exist. The server may have been restarted.'
        }), 404
    
    # Get messages since the last index
    last_index = int(request.args.get('last_index', 0))
    messages = processing_status[process_id][last_index:]
    
    # Check if done
    done = False
    content = None
    
    for msg in messages:
        if msg.startswith("DONE:"):
            done = True
            content = msg[5:]  # Remove the "DONE:" prefix
            break
    
    return jsonify({
        'messages': [msg for msg in messages if not msg.startswith("DONE:")],
        'done': done,
        'content': content,
        'last_index': last_index + len(messages)
    })

@app.route('/download/<process_id>', methods=['GET'])
def download_processed_file(process_id):
    # Get requested filename and type from query parameters
    req_filename = request.args.get('filename')
    req_type = request.args.get('type', 'file') # Default to 'file'

    # Determine if the original request was for a folder
    is_folder = process_type.get(process_id) == 'folder'
    
    print(f"Download request for process ID: {process_id}, Type: {req_type}, Requested Filename: {req_filename}, Is Folder Process: {is_folder}")

    if is_folder:
        # Handle folder download (zip)
        processed_folder_path = PROCESSED_DIR / process_id
        
        if not os.path.isdir(processed_folder_path):
            print(f"Processed folder not found: {processed_folder_path}")
            return jsonify({'error': 'Processed folder not found'}), 404

        # Use provided filename or generate a default zip name
        zip_filename = req_filename if req_filename and req_filename.lower().endswith('.zip') else f"{process_id}_processed.zip"
        zip_path = PROCESSED_DIR / zip_filename # Store zip temporarily in PROCESSED_DIR
        
        try:
            print(f"Creating zip archive: {zip_path}")
            with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(processed_folder_path):
                    for file in files:
                        file_full_path = os.path.join(root, file)
                        # Add file to zip, using relative path inside the zip
                        arcname = os.path.relpath(file_full_path, processed_folder_path)
                        zipf.write(file_full_path, arcname=arcname)
            
            print(f"Zip archive created successfully.")

            # Send the zip file
            return send_file(
                str(zip_path),
                as_attachment=True,
                download_name=zip_filename, # Use the potentially user-provided name
                mimetype='application/zip'
            )
        
        except Exception as e:
             print(f"Error creating or sending zip file: {e}", file=sys.stderr)
             traceback.print_exc(file=sys.stderr)
             return jsonify({'error': 'Failed to create or send zip archive'}), 500
        finally:
            # Clean up the temporary zip file
             if os.path.exists(zip_path):
                 try:
                     os.remove(zip_path)
                     print(f"Cleaned up temporary zip file: {zip_path}")
                 except Exception as e_clean:
                     print(f"Error cleaning up zip file {zip_path}: {e_clean}", file=sys.stderr)

    else:
        # Handle single file download (original logic)
        output_md_filename = f"{process_id}_output.md"
        file_path = PROCESSED_DIR / output_md_filename
        
        # Use provided filename or generate a default md name
        download_filename = req_filename if req_filename and req_filename.lower().endswith('.md') else output_md_filename

        if not os.path.exists(file_path):
            print(f"Processed file not found: {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        print(f"Sending single file: {file_path} as {download_filename}")
        return send_file(
            str(file_path),
            as_attachment=True,
            download_name=download_filename, # Use the potentially user-provided name
            mimetype='text/markdown'
        )

@app.route('/generate-worksheet', methods=['POST'])
def generate_worksheet():
    try:
        print("Received /generate-worksheet request")
        
        if 'file' not in request.files:
            print("No file part in the request")
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        if file.filename == '':
            print("No file selected")
            return jsonify({'error': 'No file selected'}), 400
        
        print(f"File received: {file.filename}, Content-Type: {file.content_type}")
        
        # Get form parameters  
        question_types = request.form.getlist('questionTypes[]')
        include_answers = request.form.get('includeAnswers', 'true').lower() == 'true'
        output_filename = request.form.get('outputFilename', '')
        
        print(f"Question types: {question_types}")
        print(f"Include answers: {include_answers}")
        print(f"Output filename: {output_filename}")
        
        # Generate unique ID for this process
        process_id = str(uuid.uuid4())
        processing_status[process_id] = []
        
        # Save uploaded file with absolute path
        filename = secure_filename(file.filename)
        file_path = UPLOAD_DIR / filename
        file.save(str(file_path))
        print(f"Saved file to: {file_path}")
        
        # Add first status message
        processing_status[process_id].append("File uploaded successfully")
        
        # Start processing in a separate thread
        thread = threading.Thread(
            target=process_worksheet_thread,
            args=(str(file_path), process_id, question_types, include_answers, output_filename)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing',
            'process_id': process_id
        })
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in generate_worksheet: {str(e)}", file=sys.stderr)
        print(f"Traceback: {error_traceback}", file=sys.stderr)
        return jsonify({'error': str(e), 'traceback': error_traceback}), 500

def process_worksheet_thread(file_path, process_id, question_types, include_answers, output_filename):
    try:
        # Create a custom print function that captures output
        def custom_print(message):
            print(message)  # Still print to console
            processing_status[process_id].append(message)
        
        # Determine output path
        if not output_filename:
            output_base = Path(file_path).stem + "_worksheet"
        else:
            output_base = output_filename
            
        output_path = PROCESSED_DIR / f"{process_id}_{output_base}.md"
        
        # Generate the worksheet
        custom_print("Starting worksheet generation...")
        result = generate_worksheet_from_file(
            file_path, 
            str(output_path),
            question_types,
            include_answers,
            "md",
            custom_print
        )
        
        # Read the processed content
        if result and os.path.exists(result):
            with open(result, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Add final status message
            custom_print("Worksheet generation complete!")
            processing_status[process_id].append("DONE:" + content)
            
            # Clean up temporary files
            os.remove(file_path)
        else:
            processing_status[process_id].append("ERROR: Worksheet generation failed")
            
    except Exception as e:
        error_message = f"Error processing worksheet: {str(e)}"
        print(error_message, file=sys.stderr)
        processing_status[process_id].append(f"ERROR: {error_message}")

@app.route('/download-worksheet/<process_id>', methods=['GET'])
def download_worksheet(process_id):
    try:
        format_type = request.args.get('format', 'md')
        filename = request.args.get('filename', f"{process_id}_worksheet")
        
        # Ensure filename has correct extension
        if not filename.endswith(f".{format_type}"):
            filename = f"{filename}.{format_type}"
        
        print(f"Download requested: {filename} in {format_type} format")
        
        # Find the source markdown file
        source_md_path = next((f for f in PROCESSED_DIR.glob(f"{process_id}*.md")), None)
        
        if not source_md_path:
            print(f"Source markdown file not found for process ID: {process_id}")
            return jsonify({'error': 'Worksheet not found'}), 404
            
        print(f"Source file found: {source_md_path}")
        
        # Track conversion progress
        if process_id in processing_status:
            processing_status[process_id].append(f"Preparing {format_type.upper()} download...")
        
        # If markdown is requested, just send the file
        if format_type == 'md':
            return send_file(
                source_md_path,
                as_attachment=True,
                download_name=filename,
                mimetype='text/markdown'
            )
        
        # For other formats, convert and then send
        try:
            output_path = PROCESSED_DIR / filename
            
            if format_type == 'pdf':
                from backend.Assistant import convert_md_to_pdf
                
                # Custom print function to add status updates
                def print_status(msg):
                    print(msg)
                    if process_id in processing_status:
                        processing_status[process_id].append(msg)
                
                print_status(f"Converting to PDF: {source_md_path}")
                result = convert_md_to_pdf(str(source_md_path), str(output_path), print_fn=print_status)
                mime_type = 'application/pdf'
                
            elif format_type == 'docx':
                from backend.Assistant import convert_md_to_docx
                
                # Custom print function to add status updates
                def print_status(msg):
                    print(msg)
                    if process_id in processing_status:
                        processing_status[process_id].append(msg)
                
                print_status(f"Converting to DOCX: {source_md_path}")
                result = convert_md_to_docx(str(source_md_path), str(output_path), print_fn=print_status)
                mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                
            else:
                return jsonify({'error': 'Unsupported format'}), 400
            
            if result and os.path.exists(result):
                print(f"Sending file: {result}")
                if process_id in processing_status:
                    processing_status[process_id].append(f"Download ready: {filename}")
                    
                return send_file(
                    result,
                    as_attachment=True,
                    download_name=filename,
                    mimetype=mime_type
                )
            else:
                error_msg = f"Conversion to {format_type.upper()} failed"
                print(error_msg)
                if process_id in processing_status:
                    processing_status[process_id].append(f"ERROR: {error_msg}")
                    
                return jsonify({
                    'error': 'Conversion failed',
                    'message': f"Could not convert the worksheet to {format_type.upper()}. Try downloading as Markdown instead."
                }), 500
                
        except Exception as e:
            error_msg = f"Error in download_worksheet: {str(e)}"
            print(error_msg, file=sys.stderr)
            traceback.print_exc()
            
            if process_id in processing_status:
                processing_status[process_id].append(f"ERROR: {error_msg}")
                
            return jsonify({
                'error': str(e),
                'message': "Error converting file. Try downloading as Markdown instead."
            }), 500
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Unexpected error in download_worksheet: {str(e)}", file=sys.stderr)
        print(f"Traceback: {error_traceback}", file=sys.stderr)
        return jsonify({'error': str(e), 'traceback': error_traceback}), 500

# --- New Endpoint for Folder Processing ---
@app.route('/process-folder', methods=['POST'])
def process_folder():
    try:
        print("Received /process-folder request")

        if 'files' not in request.files:
            print("No 'files' part in the request")
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            print("No files selected")
            return jsonify({'error': 'No files selected'}), 400

        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        if not pdf_files:
            print("No PDF files found in the upload")
            return jsonify({'error': 'No PDF files found in the selection'}), 400

        print(f"Received {len(pdf_files)} PDF files.")

        prompt = request.form.get('prompt', '')
        output_base_name = request.form.get('output_base_name', 'processed_folder') # Get base name
        print(f"Prompt: {prompt[:50]}..." if len(prompt) > 50 else f"Prompt: {prompt}")
        print(f"Output Base Name: {output_base_name}")

        process_id = str(uuid.uuid4())
        processing_status[process_id] = []
        process_type[process_id] = 'folder' # Mark as folder process

        # Create unique subdirectories for this folder process
        input_folder_path = UPLOAD_DIR / process_id
        output_folder_path = PROCESSED_DIR / process_id
        input_folder_path.mkdir(exist_ok=True)
        output_folder_path.mkdir(exist_ok=True) # Create output dir immediately

        saved_files = []
        for file in pdf_files:
            filename = secure_filename(file.filename)
            file_path = input_folder_path / filename
            file.save(str(file_path))
            saved_files.append(str(file_path))
            print(f"Saved file to: {file_path}")

        processing_status[process_id].append(f"Folder uploaded with {len(saved_files)} PDF files.")

        # Start folder processing in a separate thread
        thread = threading.Thread(
            target=process_folder_thread,
            args=(process_id, str(input_folder_path), str(output_folder_path), prompt, output_base_name)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'status': 'processing',
            'process_id': process_id
        })

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in process_folder: {str(e)}", file=sys.stderr)
        print(f"Traceback: {error_traceback}", file=sys.stderr)
        # Ensure status reflects error if process_id was generated
        if 'process_id' in locals() and process_id in processing_status:
             processing_status[process_id].append(f"ERROR: Failed to start processing - {str(e)}")
        return jsonify({'error': str(e), 'traceback': error_traceback}), 500

# --- New Thread Function for Folder Processing ---
def process_folder_thread(process_id, input_folder, output_folder, prompt, output_base_name):
    try:
        # Create a custom print function that captures output
        def custom_print(message):
            print(message)  # Still print to console
            processing_status[process_id].append(message)

        # Get list of PDF files
        pdf_files = glob.glob(os.path.join(input_folder, "*.pdf"))
        total_files = len(pdf_files)
        
        if total_files == 0:
            custom_print("No PDF files found in the selected folder.")
            processing_status[process_id].append("DONE:")
            return

        custom_print(f"Found {total_files} PDF files to process.")
        
        # Create output folder if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)
        
        # Track processed files
        processed_files = []
        
        # Process each file
        for i, file_path in enumerate(pdf_files):
            file_name = os.path.basename(file_path)
            output_md_filename = Path(file_name).stem + ".md"
            output_md_path = os.path.join(output_folder, output_md_filename)
            
            custom_print(f"--- Processing file {i+1}/{total_files}: {file_name} ---")
            
            try:
                # First, get the raw markdown from OCR
                result = ocr_process(file_path, output_md_path, print_fn=custom_print)
                
                # Check if result is valid
                if result:
                    output_path_str, toc = result
                    
                    processed_files.append({
                        'name': file_name,
                        'status': 'Success - Ready for section processing',
                        'output_path': output_path_str,
                        'toc': toc
                    })
                    custom_print(f"✅ Successfully processed {file_name} - Ready for section processing")
                else:
                    processed_files.append({
                        'name': file_name,
                        'status': 'Failed - No content',
                        'output_path': None
                    })
                    custom_print(f"❌ Failed to process {file_name} - No content generated")
                    
            except Exception as e:
                error_message = f"Error processing {file_name}: {str(e)}"
                print(error_message, file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                custom_print(f"❌ ERROR processing {file_name}: {str(e)}")
                processed_files.append({
                    'name': file_name,
                    'status': f'Failed - {str(e)}',
                    'output_path': None
                })

        # Create ZIP file of all processed markdown files
        zip_path = os.path.join(output_folder, f"{output_base_name}_processed.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file_info in processed_files:
                if file_info['output_path'] and os.path.exists(file_info['output_path']):
                    zipf.write(file_info['output_path'], os.path.basename(file_info['output_path']))
        
        custom_print("--- Folder processing complete ---")
        processing_status[process_id].append("All files processed.")
        processing_status[process_id].append(f"PROCESSED_FILES:{json.dumps(processed_files)}")
        processing_status[process_id].append("DONE:")

    except Exception as e:
        error_message = f"Critical error during folder processing: {str(e)}"
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        processing_status[process_id].append(f"❌ ERROR: {error_message}")
        processing_status[process_id].append("DONE:")

    finally:
        # Clean up the uploaded files sub-directory
        try:
            if os.path.exists(input_folder):
                shutil.rmtree(input_folder)
                custom_print(f"🧹 Cleaned up input folder: {input_folder}")
        except Exception as e:
             custom_print(f"⚠️ Error cleaning up input folder {input_folder}: {e}")

@app.route('/generate-toc/<process_id>', methods=['POST'])
def generate_toc_endpoint(process_id):
    try:
        data = request.get_json()
        if not data or 'markdown' not in data:
            return jsonify({'error': 'No markdown provided'}), 400
            
        # Get the cleaned markdown and ToC
        cleaned_markdown, toc = process_initial_markdown(data['markdown'])
        
        return jsonify({
            'toc': toc,
            'cleaned_markdown': cleaned_markdown
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Process sections for a file
@app.route('/process-sections/<process_id>', methods=['POST'])
def process_markdown_sections(process_id):
    try:
        # Get the markdown content with section breaks from the request
        markdown_with_breaks = request.json.get('markdown', '')
        file_path = request.json.get('filePath')  # This will be provided for folder processing
        
        if not markdown_with_breaks:
            return jsonify({'error': 'No markdown content provided'}), 400
            
        # Create a custom print function that captures output
        def custom_print(message):
            print(message)  # Still print to console
            if process_id in processing_status:
                processing_status[process_id].append(message)
        
        # Determine the base file name for creating a folder
        original_file_name = None
        output_folder = None
        
        # Handle file path standardization
        if file_path:
            # Standardize path handling
            if not os.path.isabs(file_path):
                file_path = os.path.join(PROCESSED_DIR, file_path)
                
            # Security check
            abs_path = os.path.abspath(file_path)
            processed_dir_abs = os.path.abspath(str(PROCESSED_DIR))
            if not abs_path.startswith(processed_dir_abs):
                return jsonify({'error': 'Access denied - invalid file path'}), 403
            
            # Get base file name without extension
            original_file_name = os.path.splitext(os.path.basename(abs_path))[0]
            parent_dir = os.path.dirname(abs_path)
            
            # Create a folder with the same name as the file
            output_folder = os.path.join(parent_dir, original_file_name)
        else:
            # For single file processing
            original_file_name = f"document_{process_id}"
            output_folder = os.path.join(PROCESSED_DIR, original_file_name)
        
        # Process sections and save each as a separate file
        custom_print(f"Creating folder for sections: {output_folder}")
        result = process_sections(markdown_with_breaks, output_folder, print_fn=custom_print)
        
        # Extract section files information
        section_files = result.get('section_files', [])
        
        # Make file paths relative for the response
        for file_info in section_files:
            # Make path relative to PROCESSED_DIR for response
            abs_path = file_info['file_path']
            try:
                rel_path = os.path.relpath(abs_path, PROCESSED_DIR)
                file_info['relative_path'] = rel_path
            except ValueError:
                # If paths are on different drives, keep the absolute path
                file_info['relative_path'] = abs_path
        
        return jsonify({
            'success': True,
            'section_files': section_files,
            'output_folder': output_folder,
            'original_file_name': original_file_name,
            'total_sections': len(section_files)
        })
        
    except Exception as e:
        error_message = f"Error processing sections: {str(e)}"
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'error': error_message}), 500

# Endpoint to get file content for sequential processing
@app.route('/get-file-content/<process_id>', methods=['POST'])
def get_file_content(process_id):
    try:
        data = request.get_json()
        if not data or 'filePath' not in data:
            return jsonify({'error': 'No file path provided'}), 400
            
        file_path = data['filePath']
        
        # Check if it's a relative or absolute path and standardize
        if not os.path.isabs(file_path):
            file_path = os.path.join(PROCESSED_DIR, file_path)
        
        # Security check - ensure the file is within allowed directories
        abs_path = os.path.abspath(file_path)
        processed_dir_abs = os.path.abspath(str(PROCESSED_DIR))
        if not abs_path.startswith(processed_dir_abs):
            return jsonify({'error': 'Access denied - invalid file path'}), 403
            
        # Verify the file exists
        if not os.path.exists(abs_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
            
        # Read the file content
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({
            'content': content,
            'filePath': abs_path
        })
        
    except Exception as e:
        error_message = f"Error getting file content: {str(e)}"
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'error': error_message}), 500

# Download a single file from a folder
@app.route('/download-single-file', methods=['GET'])
def download_single_file():
    try:
        file_path = request.args.get('filePath')
        file_name = request.args.get('fileName')
        
        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400
            
        # Standardize path handling
        if not os.path.isabs(file_path):
            file_path = os.path.join(PROCESSED_DIR, file_path)
            
        # Security check
        abs_path = os.path.abspath(file_path)
        processed_dir_abs = os.path.abspath(str(PROCESSED_DIR))
        if not abs_path.startswith(processed_dir_abs):
            return jsonify({'error': 'Access denied - invalid file path'}), 403
            
        if not os.path.exists(abs_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
            
        if not file_name:
            file_name = os.path.basename(abs_path)
            
        return send_file(
            abs_path,
            as_attachment=True,
            download_name=file_name,
            mimetype='text/markdown'
        )
        
    except Exception as e:
        error_message = f"Error downloading file: {str(e)}"
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'error': error_message}), 500

# Download a folder as a ZIP file
@app.route('/download-folder', methods=['GET'])
def download_folder():
    try:
        folder_path = request.args.get('folder')
        if not folder_path:
            return jsonify({'error': 'No folder path provided'}), 400
            
        # Standardize path handling
        if not os.path.isabs(folder_path):
            folder_path = os.path.join(PROCESSED_DIR, folder_path)
            
        # Security check
        abs_path = os.path.abspath(folder_path)
        processed_dir_abs = os.path.abspath(str(PROCESSED_DIR))
        if not abs_path.startswith(processed_dir_abs):
            return jsonify({'error': 'Access denied - invalid folder path'}), 403
            
        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            return jsonify({'error': f'Folder not found: {folder_path}'}), 404
            
        # Create a temporary ZIP file
        folder_name = os.path.basename(abs_path)
        zip_filename = f"{folder_name}_sections.zip"
        zip_path = os.path.join(PROCESSED_DIR, zip_filename)
        
        # Create the ZIP file
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            # Add all files in the folder to the ZIP
            for root, dirs, files in os.walk(abs_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Get relative path to preserve folder structure
                    rel_path = os.path.relpath(file_path, os.path.dirname(abs_path))
                    zipf.write(file_path, rel_path)
        
        # Send the ZIP file
        response = send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
        # Set a callback to remove the temporary ZIP file after it's sent
        @response.call_on_close
        def cleanup():
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
        
        return response
        
    except Exception as e:
        error_message = f"Error downloading folder: {str(e)}"
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'error': error_message}), 500

# --- New Route for Dropbox Link Processing ---
@app.route('/process-dropbox-link', methods=['POST'])
def process_dropbox_link():
    try:
        print("Received /process-dropbox-link request")
        data = request.get_json()
        if not data or 'dropbox_url' not in data:
            print("No Dropbox URL provided in request body")
            return jsonify({'error': 'No Dropbox URL provided'}), 400

        dropbox_url = data['dropbox_url']
        # Basic validation (optional, can be enhanced)
        if not dropbox_url.startswith('https://www.dropbox.com/'):
             print(f"Invalid Dropbox URL format: {dropbox_url}")
             return jsonify({'error': 'Invalid Dropbox URL format'}), 400
        if 'dl=1' not in dropbox_url:
             print(f"URL does not contain 'dl=1': {dropbox_url}")
             # Enforce dl=1 for direct download
             return jsonify({'error': 'Dropbox URL must be a direct download link (ending in dl=1)'}), 400

        print(f"Processing Dropbox URL: {dropbox_url}")

        # Generate unique ID for this process
        process_id = str(uuid.uuid4())
        processing_status[process_id] = []
        # Mark process type (optional, could be 'link' or adapt existing 'folder' type)
        process_type[process_id] = 'folder' # Treat downloaded/extracted content as a folder

        # Add first status message
        processing_status[process_id].append("Received Dropbox link. Starting download...")

        # Start processing in a separate thread
        thread = threading.Thread(
            target=process_link_thread,
            args=(dropbox_url, process_id)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'status': 'processing',
            'process_id': process_id
        })

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in process_dropbox_link: {str(e)}", file=sys.stderr)
        print(f"Traceback: {error_traceback}", file=sys.stderr)
        return jsonify({'error': str(e), 'traceback': error_traceback}), 500

# --- New Thread Function for Link Processing ---
def process_link_thread(dropbox_url, process_id):
    # Create a custom print function that captures output for this thread
    def custom_print(message):
        print(f"[{process_id}] {message}") # Still print to console with ID
        if process_id in processing_status:
            processing_status[process_id].append(message)
        else:
            print(f"[{process_id}] Error: Status dictionary key not found.", file=sys.stderr)

    try:
        custom_print("Downloading file from Dropbox...")
        response = requests.get(dropbox_url, stream=True, timeout=300) # Use stream=True, add timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        custom_print("Download successful. Preparing for extraction...")

        # Define the unique directory for extraction
        extract_path = STORAGE_DIR / process_id
        extract_path.mkdir(exist_ok=True)
        custom_print(f"Extracting files to: {extract_path}")

        # Extract zip file from response content
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(path=extract_path)

        custom_print("Extraction complete. Starting main processing...")

        # --- Trigger Existing Processing Logic ---
        # Determine which processing logic to call.
        # Assuming the goal is similar to the original folder processing:
        # We need an output base name. Let's derive it or use the process_id.
        output_base_name = f"processed_{process_id}"
        processed_output_folder = PROCESSED_DIR / output_base_name # Where final results will go

        # Reuse or adapt the logic from `process_folder_thread`
        # This part might need adjustments based on exactly what `process_folder_thread` does
        # and what the output of the OCR process should be named/where it should go.

        # Simplified example: Assume ocr_process can work on a directory
        # Placeholder for actual processing call - adapt as needed!
        # You might need to iterate through files in `extract_path` if `ocr_process` expects single files.
        # Or adapt `ocr_process` / `process_folder_thread` logic.

        # Example: Directly calling ocr_process if it handles directories
        # (This is a GUESS - replace with your actual logic flow)
        # result = ocr_process(str(extract_path), str(processed_output_folder), print_fn=custom_print)

        # Alternative: Adapting process_folder_thread logic structure (safer)
        num_files = len(list(extract_path.glob('**/*.pdf'))) # Count PDFs
        custom_print(f"Found {num_files} PDF files in extracted folder.")
        processed_files_info = [] # To store info about processed files

        # Iterate and process each PDF (similar structure to process_folder_thread)
        for pdf_file in extract_path.glob('**/*.pdf'):
            relative_path = pdf_file.relative_to(extract_path)
            custom_print(f"Processing file: {relative_path}")

            # Define output path for this specific file's markdown
            # Place it within a subfolder in PROCESSED_DIR related to the process_id
            md_output_dir = PROCESSED_DIR / process_id
            md_output_dir.mkdir(exist_ok=True)
            output_md_path = md_output_dir / f"{relative_path.stem}_output.md"

            try:
                # Call the core OCR process for the single file
                result = ocr_process(str(pdf_file), str(output_md_path), print_fn=custom_print)

                if result:
                    output_path_str, toc = result
                    processed_files_info.append({
                        'name': pdf_file.name,
                        'output_path': str(output_md_path),
                        'toc': toc
                    })
                    custom_print(f"Successfully processed: {pdf_file.name}")
                else:
                    custom_print(f"ERROR: OCR process failed for file: {pdf_file.name}")

            except Exception as file_e:
                 error_msg = f"Error processing file {pdf_file.name}: {str(file_e)}"
                 custom_print(f"ERROR: {error_msg}")
                 traceback.print_exc(file=sys.stderr)


        custom_print("All files processed.")
        # Signal completion similar to process_folder_thread
        processing_status[process_id].append("PROCESSED_FILES:" + json.dumps(processed_files_info))
        processing_status[process_id].append("DONE:") # Mark as done

        # Optional: Clean up the extracted folder in storage_folder after processing
        # shutil.rmtree(extract_path)
        # custom_print(f"Cleaned up temporary folder: {extract_path}")

    except requests.exceptions.RequestException as req_e:
        error_message = f"Error downloading from Dropbox: {str(req_e)}"
        custom_print(f"ERROR: {error_message}")
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    except zipfile.BadZipFile as zip_e:
        error_message = f"Error extracting zip file: {str(zip_e)}. It might be corrupted or not a zip file."
        custom_print(f"ERROR: {error_message}")
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    except Exception as e:
        error_message = f"Error in processing thread: {str(e)}"
        custom_print(f"ERROR: {error_message}") # Add error to status
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    finally:
        # Ensure DONE signal is sent even if errors occurred mid-processing
        if process_id in processing_status and not any(msg.startswith("DONE:") for msg in processing_status[process_id]):
             processing_status[process_id].append("DONE:") # Mark as done after errors

if __name__ == '__main__':
    print("Starting Flask server on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True) 