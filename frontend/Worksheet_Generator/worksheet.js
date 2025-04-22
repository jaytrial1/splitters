document.addEventListener('DOMContentLoaded', () => {
    console.log('Worksheet Generator script loaded.');

    // Define base URL to match the exact Flask server address
    const baseUrl = 'http://127.0.0.1:5000';

    const worksheetSubmit = document.getElementById('worksheet-submit');
    const worksheetLoading = document.getElementById('worksheet-loading');
    const worksheetOutputArea = document.getElementById('worksheet-output'); // The container
    const worksheetOutputPreview = document.getElementById('worksheet-output-preview'); // The div for preview
    const worksheetTip = document.getElementById('worksheet-tip');
    const worksheetFileInput = document.getElementById('worksheet-file');
    const worksheetFilenameInput = document.getElementById('worksheet-output-filename');
    const downloadWordBtn = document.getElementById('download-word');
    const downloadPdfBtn = document.getElementById('download-pdf');

    // Create a status box for displaying backend messages
    const worksheetStatusBox = document.createElement('div');
    worksheetStatusBox.id = 'worksheet-status-box';
    worksheetStatusBox.className = 'status-box';
    worksheetStatusBox.style.display = 'none';
    worksheetLoading.parentNode.insertBefore(worksheetStatusBox, worksheetLoading.nextSibling);

    // Hide output area initially
    if(worksheetOutputArea) {
        worksheetOutputArea.style.display = 'none';
    }

    const teacherTips = [
        "Use varied question types to assess different learning levels.",
        "Include real-world examples to make questions more relatable.",
        "Add an answer key section for easy grading.",
        "Consider Bloom's Taxonomy when creating questions.",
        "Proofread your worksheet carefully before distributing.",
        "Align questions with your learning objectives.",
        "Keep instructions clear and concise."
    ];

    // Global variables to track progress
    let currentProcessId = null;
    let statusCheckInterval = null;
    let lastStatusIndex = 0;

    // Function to poll for status updates
    function checkProcessStatus() {
        if (!currentProcessId) return;
        
        fetch(`${baseUrl}/process-status/${currentProcessId}?last_index=${lastStatusIndex}`)
            .then(response => {
                if (response.status === 404) {
                    console.error('Process ID not found. The server may have been restarted.');
                    clearInterval(statusCheckInterval);
                    worksheetLoading.style.display = 'none';
                    worksheetStatusBox.style.display = 'block';
                    worksheetStatusBox.innerHTML = `
                        <p class="error">Process not found</p>
                        <p class="error-hint">The server may have been restarted. Please try again.</p>
                    `;
                    return { error: 'Process not found', messages: [], done: false };
                }
                
                if (!response.ok) {
                    throw new Error('Status check failed');
                }
                return response.json();
            })
            .then(data => {
                if (data.error) return; // Skip processing if there was an error
                
                // Update status messages
                if (data.messages && data.messages.length > 0) {
                    worksheetStatusBox.style.display = 'block';
                    
                    // Show only the latest message
                    if (data.messages.length > 0) {
                        const latestMessage = data.messages[data.messages.length - 1];
                        
                        // Create/update the status display
                        if (worksheetStatusBox.querySelector('.current-status')) {
                            worksheetStatusBox.querySelector('.current-status').textContent = latestMessage;
                        } else {
                            worksheetStatusBox.innerHTML = `<p class="current-status">${latestMessage}</p>`;
                        }
                        
                        // Add a progress animation if processing is ongoing
                        if (!data.done && !worksheetStatusBox.querySelector('.progress-bar')) {
                            const progressBar = document.createElement('div');
                            progressBar.className = 'progress-bar';
                            worksheetStatusBox.appendChild(progressBar);
                        } else if (data.done && worksheetStatusBox.querySelector('.progress-bar')) {
                            worksheetStatusBox.querySelector('.progress-bar').remove();
                        }
                    }
                    
                    lastStatusIndex = data.last_index;
                }
                
                // If processing is complete
                if (data.done) {
                    clearInterval(statusCheckInterval);
                    worksheetLoading.style.display = 'none';
                    
                    if (data.content) {
                        // Convert markdown to HTML for preview
                        const renderedHTML = convertMarkdownToHTML(data.content);
                        worksheetOutputPreview.innerHTML = renderedHTML;
                        
                        // Store the raw markdown for downloads
                        worksheetOutputPreview.setAttribute('data-markdown', data.content);
                        
                        worksheetOutputArea.style.display = 'block';
                        downloadWordBtn.disabled = false;
                        downloadPdfBtn.disabled = false;
                    } else {
                        alert('Processing completed but no content was returned.');
                    }
                }
            })
            .catch(error => {
                console.error('Error checking process status:', error);
            });
    }

    // Simple markdown to HTML converter for preview
    function convertMarkdownToHTML(markdown) {
        // This is a very basic converter - for a real implementation, use a library like marked.js
        return markdown
            // Headers
            .replace(/# (.*)/g, '<h1>$1</h1>')
            .replace(/## (.*)/g, '<h2>$1</h2>')
            .replace(/### (.*)/g, '<h3>$1</h3>')
            // Bold and italics
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Lists
            .replace(/^\s*\- (.*)/gm, '<li>$1</li>')
            // Line breaks
            .replace(/\n/g, '<br>');
    }

    if (worksheetSubmit) {
        worksheetSubmit.addEventListener('click', () => {
             console.log('Generate Worksheet button clicked.');
            // --- Input Validation ---
            if (!worksheetFileInput.files || worksheetFileInput.files.length === 0) {
                alert('Please select a source file first.');
                return;
            }
            const selectedQTypes = Array.from(document.querySelectorAll('input[name="qtype"]:checked'))
                                       .map(cb => cb.value);
            if (selectedQTypes.length === 0) {
                alert('Please select at least one question type.');
                return;
            }
             if (!worksheetFilenameInput.value.trim()) {
                alert('Please enter an output filename.');
                worksheetFilenameInput.focus();
                return;
            }

            // Get the answer option selection
            const includeAnswers = document.querySelector('input[name="include-answers"]:checked').value === 'with-answers';
            console.log('Include answers:', includeAnswers);

            // --- Update UI for Loading State ---
            const randomTip = teacherTips[Math.floor(Math.random() * teacherTips.length)];
            if(worksheetTip) worksheetTip.textContent = `Generating worksheet... Tip: ${randomTip}`;
            if(worksheetLoading) worksheetLoading.style.display = 'block';
            if(worksheetOutputArea) worksheetOutputArea.style.display = 'none';
            if(worksheetStatusBox) {
                worksheetStatusBox.style.display = 'none';
                worksheetStatusBox.innerHTML = '';
            }
            if(downloadWordBtn) downloadWordBtn.disabled = true;
            if(downloadPdfBtn) downloadPdfBtn.disabled = true;
            
            // Reset status tracking
            lastStatusIndex = 0;
            if (statusCheckInterval) {
                clearInterval(statusCheckInterval);
            }

            // Create FormData for file upload
            const formData = new FormData();
            formData.append('file', worksheetFileInput.files[0]);
            
            // Add question types as an array
            selectedQTypes.forEach(type => {
                formData.append('questionTypes[]', type);
            });
            
            // Add other parameters
            formData.append('includeAnswers', includeAnswers);
            formData.append('outputFilename', worksheetFilenameInput.value.trim());

            // Send to backend
            fetch(`${baseUrl}/generate-worksheet`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    console.error('Server response:', response.status, response.statusText);
                    return response.text().then(text => {
                        throw new Error(`Worksheet generation failed: ${response.status} ${response.statusText}${text ? ' - ' + text : ''}`);
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
                console.error('Error generating worksheet:', error);
                worksheetLoading.style.display = 'none';
                worksheetStatusBox.style.display = 'block';
                worksheetStatusBox.innerHTML = `
                    <p class="error">Error: ${error.message}</p>
                    <p class="error-hint">Check that the Flask server is running at http://127.0.0.1:5000</p>
                `;
                alert('Error generating worksheet: ' + error.message);
            });
        });
    }

    // Function to download worksheet in specified format
    function downloadWorksheet(format) {
        if (!currentProcessId) return;
        
        const filenameBase = worksheetFilenameInput.value.trim() || 'generated_worksheet';
        const extension = format === 'word' ? 'docx' : format;
        const finalFilename = filenameBase.endsWith(`.${extension}`) ? filenameBase : `${filenameBase}.${extension}`;
        
        // Show a downloading message
        worksheetStatusBox.style.display = 'block';
        worksheetStatusBox.innerHTML = `<p class="current-status">Preparing ${format.toUpperCase()} download...</p>
        <div class="progress-bar"></div>`;
        
        // Start polling for status updates during conversion
        const downloadStatusInterval = setInterval(() => {
            fetch(`${baseUrl}/process-status/${currentProcessId}?last_index=${lastStatusIndex}`)
                .then(response => {
                    if (!response.ok) return {};
                    return response.json();
                })
                .then(data => {
                    if (data.messages && data.messages.length > 0) {
                        lastStatusIndex = data.last_index;
                        
                        // Show only the latest message
                        const latestMessage = data.messages[data.messages.length - 1];
                        worksheetStatusBox.querySelector('.current-status').textContent = latestMessage;
                        
                        // If there's an error message, stop the polling and show error
                        if (latestMessage.startsWith('ERROR:')) {
                            clearInterval(downloadStatusInterval);
                            worksheetStatusBox.querySelector('.progress-bar').remove();
                            worksheetStatusBox.querySelector('.current-status').className = 'error';
                            
                            const errorHint = document.createElement('p');
                            errorHint.className = 'error-hint';
                            errorHint.textContent = 'Try downloading as Markdown instead.';
                            worksheetStatusBox.appendChild(errorHint);
                        }
                        
                        // If download is ready, open the URL
                        if (latestMessage.startsWith('Download ready:')) {
                            clearInterval(downloadStatusInterval);
                            
                            // Create the download URL
                            const downloadUrl = `${baseUrl}/download-worksheet/${currentProcessId}?format=${format}&filename=${encodeURIComponent(finalFilename)}`;
                            
                            // Open the download in a new tab to avoid interrupting the current page
                            window.open(downloadUrl, '_blank');
                            
                            // Update status
                            worksheetStatusBox.innerHTML = `<p class="current-status">Download started!</p>`;
                            setTimeout(() => {
                                worksheetStatusBox.style.display = 'none';
                            }, 3000);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error checking download status:', error);
                });
        }, 1000);
        
        // Set a timeout to prevent endless polling if something goes wrong
        setTimeout(() => {
            if (downloadStatusInterval) {
                clearInterval(downloadStatusInterval);
                if (worksheetStatusBox.querySelector('.progress-bar')) {
                    worksheetStatusBox.innerHTML = `
                        <p class="error">Download timed out</p>
                        <p class="error-hint">Try downloading directly:</p>
                    `;
                    
                    // Add a direct download link as fallback
                    const directLink = document.createElement('a');
                    directLink.href = `${baseUrl}/download-worksheet/${currentProcessId}?format=${format}&filename=${encodeURIComponent(finalFilename)}`;
                    directLink.textContent = `Download ${format.toUpperCase()} directly`;
                    directLink.className = 'direct-download-link';
                    directLink.setAttribute('target', '_blank');
                    worksheetStatusBox.appendChild(directLink);
                }
            }
        }, 30000); // 30 second timeout
        
        // Create the download URL
        const downloadUrl = `${baseUrl}/download-worksheet/${currentProcessId}?format=${format}&filename=${encodeURIComponent(finalFilename)}`;
        
        // Trigger download in an iframe to avoid navigating away from the page
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = downloadUrl;
        document.body.appendChild(iframe);
        
        // Remove the iframe after a while
        setTimeout(() => {
            if (document.body.contains(iframe)) {
                document.body.removeChild(iframe);
            }
        }, 5000);
    }

    if (downloadWordBtn) {
        downloadWordBtn.addEventListener('click', () => {
            if (!downloadWordBtn.disabled) {
                downloadWorksheet('docx');
            }
        });
    }
    if (downloadPdfBtn) {
        downloadPdfBtn.addEventListener('click', () => {
             if (!downloadPdfBtn.disabled) {
                 downloadWorksheet('pdf');
            }
        });
    }
}); 