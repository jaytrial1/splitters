Here's the whole structure of the project files :

frontend folder :
index.html (Main index file - home page)
styles.css (main page styling)
script.js (main page's javascript)

frontend/Text_to_Docs folder :
text2doc.html
text2doc.css
text2doc.js

frontend/Worksheet_Generator :
worksheet.html
worksheet.css
worksheet.js

backend folder :
app.py (flask app file)
Improve_text.py (python file to clean and format the markdown file into proper format)
final_ocr.py (python file to convert pdf into md)
Assistant.py (worksheet generator)


Working of Text_to_Docs

- User would give the pdf file and the prompt to format the file properly
- at the backend first of all the pdf would be sent to the ocr_formatting.py so that it can be converted to md format
- then the md format would be sent to the AI along with the predefined prompt with the optional additional prompt given by the user so that AI can process it and make an elegant markdown file and give it as an output.
- then the output markdown file is shown to the user on the frontend and gives the ability to do some kind of changes before downloading.
- all this working should be done in single python file.
- When user hits download the user should be prompted with a popup of their file explorer to ask them where they want to save their file.

Working of Worksheet

- the markdown file given by the user should would be sent to AI along with the prompt made as per the selection of the user of which kind of questions they want to include and whether they want to have a worksheet with or without answers
- AI would give the output in the markdown only and again the user would have the ability to make changes as well as the ability to download the output in pdf or word format.