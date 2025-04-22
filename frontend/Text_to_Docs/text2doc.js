document.addEventListener('DOMContentLoaded', () => {
    console.log('Text2Doc script loaded.');

    // Define base URL to match the exact Flask server address
    const baseUrl = 'http://127.0.0.1:5000';

    const text2docSubmit = document.getElementById('text2doc-submit');
    const text2docLoading = document.getElementById('text2doc-loading');
    const text2docOutputArea = document.getElementById('text2doc-output');
    const text2docPreviewArea = document.getElementById('text2doc-preview-area');
    const tocPreview = document.getElementById('toc-preview');
    const addSectionBreakBtn = document.getElementById('add-section-break');
    const processSectionsBtn = document.getElementById('process-sections');
    const downloadMdBtn = document.getElementById('download-md');
    const text2docFileInput = document.getElementById('text2doc-file');
    const text2docFilenameInput = document.getElementById('text2doc-output-filename');
    const text2docPrompt = document.getElementById('text2doc-prompt');
    const text2docStatusBox = document.createElement('div');
    
    // Create a status box for displaying backend messages
    text2docStatusBox.id = 'text2doc-status-box';
    text2docStatusBox.className = 'status-box';
    text2docStatusBox.style.display = 'none';
    text2docLoading.parentNode.insertBefore(text2docStatusBox, text2docLoading.nextSibling);

    // Hide output area initially
    if (text2docOutputArea) {
        text2docOutputArea.style.display = 'none';
    }

    // Global variables to track progress
    let currentProcessId = null;
    let statusCheckInterval = null;
    let lastStatusIndex = 0;
    let isFolderUpload = false;
    let currentMarkdown = '';
    let currentToc = '';
    // Add file queue variables
    let fileQueue = [];
    let currentFileIndex = -1;
    let folderProcessId = null;
    
    // Try to restore session if page was refreshed during processing
    function tryRestoreSession() {
        const savedSession = sessionStorage.getItem('text2docSession');
        if (savedSession) {
            try {
                const session = JSON.parse(savedSession);
                currentProcessId = session.processId;
                isFolderUpload = session.isFolderUpload;
                fileQueue = session.fileQueue || [];
                currentFileIndex = session.currentFileIndex || -1;
                folderProcessId = session.folderProcessId;
                lastStatusIndex = session.lastStatusIndex || 0;
                
                if (isFolderUpload && fileQueue.length > 0 && currentProcessId) {
                    // Restart status check
                    statusCheckInterval = setInterval(checkProcessStatus, 1000);
                    
                    text2docStatusBox.style.display = 'block';
                    text2docStatusBox.innerHTML = '<p class="current-status">Restoring previous session...</p>';
                    
                    // If we were in the middle of a file, continue with it
                    if (currentFileIndex >= 0 && currentFileIndex < fileQueue.length) {
                        setTimeout(() => {
                            processNextFileInQueue(true); // true means we're restoring
                        }, 1500);
                    }
                    return true;
                }
            } catch (e) {
                console.error('Error restoring session:', e);
                sessionStorage.removeItem('text2docSession');
            }
        }
        return false;
    }
    
    // Save current session state
    function saveSession() {
        try {
            const session = {
                processId: currentProcessId,
                isFolderUpload: isFolderUpload,
                fileQueue: fileQueue,
                currentFileIndex: currentFileIndex,
                folderProcessId: folderProcessId,
                lastStatusIndex: lastStatusIndex
            };
            sessionStorage.setItem('text2docSession', JSON.stringify(session));
        } catch (e) {
            console.error('Error saving session:', e);
        }
    }
    
    // Check for a previous session on page load
    if (tryRestoreSession()) {
        console.log('Restored previous session');
    }

    // Function to add section break at cursor position
    function addSectionBreak() {
        const textarea = text2docPreviewArea;
        const cursorPos = textarea.selectionStart;
        const text = textarea.value;
        
        // Insert section break at cursor position
        const newText = text.substring(0, cursorPos) + 
                       '\n\n=====Section Break=====\n\n' + 
                       text.substring(cursorPos);
        
        textarea.value = newText;
        
        // Restore cursor position after the section break
        const newCursorPos = cursorPos + '\n\n=====Section Break=====\n\n'.length;
        textarea.setSelectionRange(newCursorPos, newCursorPos);
    }

    // Function to process the next file in queue
    function processNextFileInQueue(isRestoring) {
        if (!isRestoring) {
            currentFileIndex++;
        }
        
        // Save session state
        saveSession();
        
        // If we've processed all files, show completion message
        if (currentFileIndex >= fileQueue.length) {
            text2docStatusBox.style.display = 'block';
            text2docStatusBox.innerHTML = '<p class="current-status">✅ All files have been processed! You can download the complete ZIP.</p>';
            downloadMdBtn.disabled = false;
            downloadMdBtn.textContent = 'Download All Files (ZIP)';
            return;
        }
        
        const fileInfo = fileQueue[currentFileIndex];
        
        // Display the current file information
        text2docStatusBox.style.display = 'block';
        text2docStatusBox.innerHTML = `<p class="current-status">Editing file ${currentFileIndex + 1} of ${fileQueue.length}: ${fileInfo.name}</p>`;
        
        // Fetch the file content
        fetch(`${baseUrl}/get-file-content/${folderProcessId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filePath: fileInfo.output_path
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Update UI with file content and TOC
            currentMarkdown = data.content;
            text2docPreviewArea.value = currentMarkdown;
            text2docOutputArea.style.display = 'block';
            
            // Display TOC if available
            if (fileInfo.toc) {
                currentToc = fileInfo.toc;
                tocPreview.innerHTML = currentToc;
            } else {
                tocPreview.innerHTML = '<p>No Table of Contents available</p>';
            }
            
            // Enable editing controls
            addSectionBreakBtn.disabled = false;
            processSectionsBtn.disabled = false;
            
            // Update the UI to show file progress
            const progressElement = document.createElement('div');
            progressElement.className = 'file-progress';
            progressElement.textContent = `File ${currentFileIndex + 1} of ${fileQueue.length}`;
            
            const nextButton = document.createElement('button');
            nextButton.textContent = 'Skip to Next File';
            nextButton.className = 'btn';
            nextButton.onclick = () => processNextFileInQueue(false);
            
            const controlsDiv = document.createElement('div');
            controlsDiv.className = 'file-controls';
            controlsDiv.appendChild(progressElement);
            controlsDiv.appendChild(nextButton);
            
            if (document.querySelector('.file-controls')) {
                document.querySelector('.file-controls').replaceWith(controlsDiv);
            } else {
                text2docOutputArea.insertBefore(controlsDiv, text2docOutputArea.firstChild);
            }
        })
        .catch(error => {
            console.error('Error loading file content:', error);
            text2docStatusBox.innerHTML = `<p class="current-status">❌ Error loading file: ${error.message}</p>`;
            
            // Mark this file as failed in the queue
            if (fileQueue[currentFileIndex]) {
                fileQueue[currentFileIndex].error = error.message;
                fileQueue[currentFileIndex].processed = false;
                saveSession();
            }
            
            // Add skip button
            const skipButton = document.createElement('button');
            skipButton.textContent = 'Skip to Next File';
            skipButton.onclick = () => processNextFileInQueue(false);
            text2docStatusBox.appendChild(skipButton);
            
            // Skip to next file on error after 5 seconds if user doesn't click
            setTimeout(() => {
                if (currentFileIndex < fileQueue.length && fileQueue[currentFileIndex] && fileQueue[currentFileIndex].error) {
                    processNextFileInQueue(false);
                }
            }, 5000);
        });
    }

    // Add CSS for new UI elements
    function addDynamicStyles() {
        const styleElement = document.createElement('style');
        styleElement.textContent = `
            .file-controls {
                background: #f5f5f5;
                padding: 10px;
                margin-bottom: 15px;
                border-radius: 5px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .file-progress {
                font-weight: bold;
                color: #333;
            }
            .primary-btn {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
            .warning-btn {
                background-color: #ff9800;
            }
            .error-message {
                color: #d32f2f;
                background-color: #ffebee;
                padding: 10px;
                border-radius: 4px;
                margin: 10px 0;
            }
            .section-files-list {
                margin-top: 15px;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                background-color: #f9f9f9;
                max-height: 300px;
                overflow-y: auto;
            }
            .section-files-list h3 {
                margin-top: 0;
                border-bottom: 1px solid #ddd;
                padding-bottom: 5px;
            }
            .section-files-list ul {
                list-style-type: none;
                padding-left: 0;
            }
            .section-files-list li {
                padding: 5px 0;
                border-bottom: 1px solid #eee;
            }
            .section-files-list li:last-child {
                border-bottom: none;
            }
            .section-files-list a {
                text-decoration: none;
                color: #2196F3;
            }
            .section-files-list a:hover {
                text-decoration: underline;
            }
        `;
        document.head.appendChild(styleElement);
    }

    // Call the function to add styles
    addDynamicStyles();
    
    // Global variable to store last processed folder for download
    window.lastProcessedFolder = null;

    // Add error handling in processSections function
    async function processSections() {
        if (!currentProcessId) return;
        
        const markdownWithBreaks = text2docPreviewArea.value;
        const originalMarkdown = markdownWithBreaks; // Save original for error recovery
        
        try {
            // Show a processing message
            text2docStatusBox.style.display = 'block';
            text2docStatusBox.innerHTML = '<p class="current-status">Processing sections...</p>';
            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar';
            text2docStatusBox.appendChild(progressBar);
            
            const response = await fetch(`${baseUrl}/process-sections/${currentProcessId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    markdown: markdownWithBreaks,
                    filePath: isFolderUpload ? fileQueue[currentFileIndex].output_path : null
                })
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error (${response.status}): ${errorText}`);
            }
            
            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Display the processed section files
            const sectionFiles = data.section_files || [];
            const outputFolder = data.output_folder || '';
            const totalSections = data.total_sections || 0;
            
            // Create a section files list in the preview area
            let sectionFilesHtml = `# Processed ${totalSections} Sections\n\n`;
            sectionFilesHtml += `## Folder: ${outputFolder}\n\n`;
            sectionFilesHtml += "| Section | File |\n";
            sectionFilesHtml += "|---------|------|\n";
            
            sectionFiles.forEach(file => {
                sectionFilesHtml += `| ${file.title} | ${file.file_name} |\n`;
            });
            
            // Update the preview area with section files list
            text2docPreviewArea.value = sectionFilesHtml;
            
            // If we're processing a file in a folder, update the queue item
            if (isFolderUpload && fileQueue[currentFileIndex]) {
                fileQueue[currentFileIndex].processed = true;
                fileQueue[currentFileIndex].sectionFiles = sectionFiles;
                fileQueue[currentFileIndex].outputFolder = outputFolder;
                saveSession();
            }
            
            // Store the output folder for download later
            window.lastProcessedFolder = outputFolder;
            
            // Update status to show completion
            text2docStatusBox.innerHTML = `
                <p class="current-status">✅ All sections processed successfully!</p>
                <p>Created ${totalSections} section files in folder: ${data.original_file_name}</p>
            `;
            
            // Create a download all button
            const downloadFolderBtn = document.createElement('button');
            downloadFolderBtn.textContent = 'Download All Sections';
            downloadFolderBtn.className = 'btn primary-btn';
            downloadFolderBtn.onclick = () => {
                // Download the entire folder as a zip
                window.location.href = `${baseUrl}/download-folder?folder=${encodeURIComponent(outputFolder)}`;
            };
            text2docStatusBox.appendChild(downloadFolderBtn);
            
            // Add section files list element
            const sectionFilesList = document.createElement('div');
            sectionFilesList.className = 'section-files-list';
            sectionFilesList.innerHTML = `
                <h3>Section Files (${totalSections})</h3>
                <ul>
                    ${sectionFiles.map(file => `<li>
                        <a href="${baseUrl}/download-single-file?filePath=${encodeURIComponent(file.file_path)}&fileName=${encodeURIComponent(file.file_name)}" target="_blank">
                            ${file.title} (${file.file_name})
                        </a>
                    </li>`).join('')}
                </ul>
            `;
            text2docStatusBox.appendChild(sectionFilesList);
            
            // Enable move to next file button for folder processing
            if (isFolderUpload) {
                const nextFileBtn = document.createElement('button');
                nextFileBtn.textContent = 'Continue to Next File';
                nextFileBtn.className = 'btn primary-btn';
                nextFileBtn.style.marginTop = '15px';
                nextFileBtn.onclick = () => processNextFileInQueue(false);
                text2docStatusBox.appendChild(nextFileBtn);
            }
            
            // Enable download button for all sections
            downloadMdBtn.disabled = false;
            downloadMdBtn.textContent = 'Download All Sections (ZIP)';
            
        } catch (error) {
            console.error('Error processing sections:', error);
            
            // Restore original content
            text2docPreviewArea.value = originalMarkdown;
            
            text2docStatusBox.innerHTML = `<p class="current-status">❌ Error: ${error.message}</p>`;
            
            // Add retry button
            const retryBtn = document.createElement('button');
            retryBtn.textContent = 'Retry Processing';
            retryBtn.className = 'btn';
            retryBtn.onclick = processSections;
            text2docStatusBox.appendChild(retryBtn);
            
            // Add skip button for folder processing
            if (isFolderUpload) {
                const skipBtn = document.createElement('button');
                skipBtn.textContent = 'Skip to Next File';
                skipBtn.className = 'btn';
                skipBtn.onclick = () => processNextFileInQueue(false);
                text2docStatusBox.appendChild(document.createTextNode(' '));
                text2docStatusBox.appendChild(skipBtn);
            }
        }
    }

    // Update checkProcessStatus to save session
    function checkProcessStatus() {
        if (!currentProcessId) return;
        
        fetch(`${baseUrl}/process-status/${currentProcessId}?last_index=${lastStatusIndex}`)
            .then(response => {
                if (!response.ok) return {};
                return response.json();
            })
            .then(data => {
                if (data.error) return; // Skip processing if there was an error
                
                // Update status messages
                if (data.messages && data.messages.length > 0) {
                    let displayToc = false;
                    let readyForSections = false;
                    let markdownContent = '';
                    let tocContent = '';
                    let processedFiles = null;
                    
                    text2docStatusBox.style.display = 'block';
                    
                    // Process each message
                    for (const message of data.messages) {
                        // Check for special message formats
                        if (message.startsWith('READY_FOR_SECTIONS:')) {
                            readyForSections = true;
                            markdownContent = message.substring('READY_FOR_SECTIONS:'.length);
                            continue;
                        }
                        
                        if (message.startsWith('TOC:')) {
                            displayToc = true;
                            tocContent = message.substring('TOC:'.length);
                            continue;
                        }
                        
                        // Handle folder processing completion
                        if (message.startsWith('PROCESSED_FILES:')) {
                            const parsedFiles = JSON.parse(message.substring('PROCESSED_FILES:'.length));
                            isFolderUpload = true;
                            processedFiles = parsedFiles;
                            continue;
                        }
                        
                        // Handle process completion
                        if (message.startsWith('DONE:')) {
                            data.done = true;
                            continue;
                        }
                    }
                    
                    // Display the latest non-special message
                    const regularMessages = data.messages.filter(msg => 
                        !msg.startsWith('READY_FOR_SECTIONS:') && 
                        !msg.startsWith('TOC:') && 
                        !msg.startsWith('PROCESSED_FILES:') && 
                        !msg.startsWith('DONE:')
                    );
                    
                    if (regularMessages.length > 0) {
                        const latestMessage = regularMessages[regularMessages.length - 1];
                        
                        // Create/update the status display
                        if (text2docStatusBox.querySelector('.current-status')) {
                            text2docStatusBox.querySelector('.current-status').textContent = latestMessage;
                        } else {
                            text2docStatusBox.innerHTML = `<p class="current-status">${latestMessage}</p>`;
                        }
                        }
                        
                        // Add a progress animation if processing is ongoing
                        if (!data.done && !text2docStatusBox.querySelector('.progress-bar')) {
                            const progressBar = document.createElement('div');
                            progressBar.className = 'progress-bar';
                            text2docStatusBox.appendChild(progressBar);
                        } else if (data.done && text2docStatusBox.querySelector('.progress-bar')) {
                            text2docStatusBox.querySelector('.progress-bar').remove();
                    }
                    
                    // Handle folder processing - setup file queue
                    if (isFolderUpload && processedFiles && processedFiles.length > 0 && fileQueue.length === 0) {
                        folderProcessId = currentProcessId;
                        fileQueue = processedFiles;
                        
                        // Save session state
                        saveSession();
                        
                        // Process first file after initial OCR is complete
                        if (data.done) {
                            clearInterval(statusCheckInterval);
                            text2docLoading.style.display = 'none';
                            processNextFileInQueue(false);
                        }
                    }
                    
                    // For single file processing
                    if (!isFolderUpload) {
                        // Handle markdown content if ready for sections
                        if (readyForSections) {
                            currentMarkdown = markdownContent;
                            text2docPreviewArea.value = currentMarkdown;
                            text2docOutputArea.style.display = 'block';
                            addSectionBreakBtn.disabled = false;
                            processSectionsBtn.disabled = false;
                        }
                        
                        // Handle TOC content
                        if (displayToc && tocContent) {
                            currentToc = tocContent;
                            tocPreview.innerHTML = tocContent;
                        }
                    }
                    
                    lastStatusIndex = data.last_index;
                }
                
                // If processing is complete for single file
                if (!isFolderUpload && data.done) {
                    clearInterval(statusCheckInterval);
                    text2docLoading.style.display = 'none';
                }
            })
            .catch(error => {
                console.error('Error checking process status:', error);
                // On network error, don't clear interval - allow reconnection attempts
            });
    }

    // Add event listeners for new buttons
    if (addSectionBreakBtn) {
        addSectionBreakBtn.addEventListener('click', addSectionBreak);
    }
    
    if (processSectionsBtn) {
        processSectionsBtn.addEventListener('click', processSections);
    }

    // Update start processing function to clear any previous session
    if (text2docSubmit) {
        text2docSubmit.addEventListener('click', () => {
            console.log('Process Document/Folder button clicked.');
            
            // Clear any previous session
            sessionStorage.removeItem('text2docSession');
            
            const files = text2docFileInput.files;
            if (!files || files.length === 0) {
                alert('Please select a PDF file or a folder containing PDF files.');
                return;
            }
            if (!text2docFilenameInput.value.trim()) {
                alert('Please enter an output filename or base name.');
                text2docFilenameInput.focus();
                return;
            }

            // Determine if it's a folder upload
            isFolderUpload = files.length > 1 || (files.length === 1 && files[0].webkitRelativePath !== "");
            console.log(`Folder upload detected: ${isFolderUpload}`);

            // Show loading, hide output area, clear status box, disable buttons
            text2docLoading.style.display = 'block';
            text2docOutputArea.style.display = 'none';
            text2docStatusBox.style.display = 'none';
            text2docStatusBox.innerHTML = '';
            downloadMdBtn.disabled = true;
            addSectionBreakBtn.disabled = true;
            processSectionsBtn.disabled = true;
            
            // Reset status tracking
            lastStatusIndex = 0;
            currentProcessId = null;
            if (statusCheckInterval) {
                clearInterval(statusCheckInterval);
            }

            // Create FormData for file upload
            const formData = new FormData();
            const pdfFiles = [];
            for (let i = 0; i < files.length; i++) {
                // Only include PDF files
                if (files[i].type === 'application/pdf' || files[i].name.toLowerCase().endsWith('.pdf')) {
                    formData.append('files', files[i], files[i].name); // Use 'files' for multiple files
                    pdfFiles.push(files[i].name);
                } else if (isFolderUpload) {
                    console.warn(`Skipping non-PDF file: ${files[i].name}`);
                }
            }

            if (pdfFiles.length === 0) {
                alert('No PDF files found in the selection.');
                text2docLoading.style.display = 'none';
                return;
            }

            console.log(`Uploading ${pdfFiles.length} PDF files:`, pdfFiles);

            formData.append('prompt', text2docPrompt.value);
            formData.append('output_base_name', text2docFilenameInput.value.trim()); // Add base name for folder processing

            // Choose the correct endpoint
            const endpoint = isFolderUpload ? `${baseUrl}/process-folder` : `${baseUrl}/process-pdf`;
            // If it's a single file, rename 'files' back to 'file' for the existing endpoint
            if (!isFolderUpload && formData.has('files')) {
                 formData.append('file', formData.get('files'));
                 formData.delete('files');
            }

            // Send to backend
            fetch(endpoint, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    console.error('Server response:', response.status, response.statusText);
                    return response.text().then(text => {
                        throw new Error(`Upload failed: ${response.status} ${response.statusText}${text ? ' - ' + text : ''}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                console.log('Processing started:', data);
                if (data.process_id) {
                    currentProcessId = data.process_id;
                    // Start checking for status updates
                    statusCheckInterval = setInterval(checkProcessStatus, 1000);
                } else {
                    throw new Error('No process ID returned');
                }
            })
            .catch(error => {
                console.error('Error uploading file(s):', error);
                text2docLoading.style.display = 'none';
                text2docStatusBox.style.display = 'block';
                text2docStatusBox.innerHTML = `
                    <p class="error">Error: ${error.message}</p>
                    <p class="error-hint">Check that the Flask server is running at http://127.0.0.1:5000</p>
                `;
                alert('Error uploading file(s): ' + error.message);
            });
        });
    }

    // Add event listener for the Markdown/ZIP download button
    if (downloadMdBtn) {
        downloadMdBtn.addEventListener('click', () => {
            console.log('Download button clicked.');
            if (!downloadMdBtn.disabled && currentProcessId) {
                const baseFilename = text2docFilenameInput.value.trim();
                let downloadUrl;

                if (isFolderUpload) {
                    // Check if we're downloading a specific file or the complete folder
                    if (currentFileIndex >= 0 && currentFileIndex < fileQueue.length) {
                        // Get the current file's output folder
                        const currentFile = fileQueue[currentFileIndex];
                        if (currentFile.outputFolder) {
                            // Download the processed sections folder
                            downloadUrl = `${baseUrl}/download-folder?folder=${encodeURIComponent(currentFile.outputFolder)}`;
                            window.location.href = downloadUrl;
                            return;
                        }
                        
                        // Fall back to downloading the original file if no sections folder
                        const fileName = currentFile.name.replace('.pdf', '.md');
                        downloadUrl = `${baseUrl}/download-single-file?filePath=${encodeURIComponent(currentFile.output_path)}&fileName=${encodeURIComponent(fileName)}`;
                    } else {
                        // Download complete folder as ZIP
                        const downloadFilename = baseFilename ? `${baseFilename}_processed.zip` : `processed_files_${currentProcessId}.zip`;
                    downloadUrl = `${baseUrl}/download/${currentProcessId}?type=folder&filename=${encodeURIComponent(downloadFilename)}`;
                    }
                } else {
                    // For single files, download the sections folder if available
                    if (window.lastProcessedFolder) {
                        downloadUrl = `${baseUrl}/download-folder?folder=${encodeURIComponent(window.lastProcessedFolder)}`;
                    } else {
                        // Fall back to downloading the single file
                        const downloadFilename = baseFilename ? (baseFilename.endsWith('.md') ? baseFilename : `${baseFilename}.md`) : `processed_document_${currentProcessId}.md`;
                    downloadUrl = `${baseUrl}/download/${currentProcessId}?type=file&filename=${encodeURIComponent(downloadFilename)}`;
                    }
                }
                
                window.location.href = downloadUrl;
            }
        });
    }
}); 