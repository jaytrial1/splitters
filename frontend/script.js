document.addEventListener('DOMContentLoaded', () => {
    console.log('Home page script loaded.');
    
    // Add subtle hover effect to tool cards
    const toolCards = document.querySelectorAll('.tool-card');
    
    toolCards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.borderColor = '#007bff';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.borderColor = '#e9ecef';
        });
    });
    
    // Attempt to connect to the server to check if it's running
    fetch('/') // Use relative path for deployment
        .then(response => {
            console.log('Server connection check successful.');
        })
        .catch(error => {
            console.warn('Server might not be running:', error);
            
            // Add a discreet warning if server appears to be offline
            const container = document.querySelector('.container');
            if (container) {
                const warningBox = document.createElement('div');
                warningBox.className = 'server-warning';
                warningBox.innerHTML = `
                    <p>⚠️ Server connection check failed. Make sure the Flask server is running.</p>
                    <p><code>python app.py</code></p>
                `;
                container.prepend(warningBox);
                
                // Add inline styles for the warning
                const style = document.createElement('style');
                style.textContent = `
                    .server-warning {
                        background-color: #fff3cd;
                        color: #856404;
                        padding: 10px 15px;
                        border-radius: 4px;
                        margin-bottom: 20px;
                        text-align: center;
                        font-size: 0.9em;
                    }
                    
                    .server-warning code {
                        background-color: #f8f9fa;
                        padding: 3px 5px;
                        border-radius: 3px;
                        font-family: monospace;
                    }
                `;
                document.head.appendChild(style);
            }
        });
}); 