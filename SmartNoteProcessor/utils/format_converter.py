import logging
import re
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class FormatConverter:
    """
    Converts note content to different output formats (Markdown, LaTeX, HTML).
    Also handles adding hyperlinks between related topics.
    """
    
    def __init__(self):
        """Initialize the format converter."""
        pass
    
    def convert(self, title: str, content: str, output_format: str) -> str:
        """
        Convert note content to the specified output format.
        
        Args:
            title: Title of the note
            content: Content of the note (assumed to be in Markdown format)
            output_format: Target format ('markdown', 'latex', or 'html')
            
        Returns:
            Converted content in the specified format
        """
        # Clean up the content
        content = content.strip()
        
        if output_format.lower() == 'markdown':
            # Already in Markdown format, just ensure proper title formatting
            if not content.startswith('# '):
                content = f"# {title}\n\n{content}"
            return content
            
        elif output_format.lower() == 'latex':
            return self._markdown_to_latex(title, content)
            
        elif output_format.lower() == 'html':
            return self._markdown_to_html(title, content)
            
        else:
            logger.warning(f"Unsupported format '{output_format}', defaulting to Markdown")
            return content
    
    def _markdown_to_latex(self, title: str, content: str) -> str:
        """
        Convert Markdown content to LaTeX format.
        
        Args:
            title: Note title
            content: Markdown content
            
        Returns:
            Content in LaTeX format
        """
        # Start with LaTeX document structure
        latex = f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{hyperref}}
\\usepackage{{graphicx}}
\\usepackage{{amssymb,amsmath}}

\\title{{{title}}}
\\date{{}}

\\begin{{document}}

\\maketitle

"""
        
        # Process content line by line
        lines = content.split('\n')
        in_list = False
        in_code_block = False
        list_type = None
        
        for line in lines:
            # Skip line if it's the title (we already added it)
            if line.strip() == f"# {title}":
                continue
                
            # Handle code blocks
            if line.strip().startswith('```'):
                if not in_code_block:
                    latex += "\\begin{verbatim}\n"
                    in_code_block = True
                else:
                    latex += "\\end{verbatim}\n\n"
                    in_code_block = False
                continue
            
            if in_code_block:
                latex += line + "\n"
                continue
            
            # Handle headers
            if line.strip().startswith('# '):
                latex += f"\\section{{{line.strip().lstrip('# ')}}}\n\n"
            elif line.strip().startswith('## '):
                latex += f"\\subsection{{{line.strip().lstrip('## ')}}}\n\n"
            elif line.strip().startswith('### '):
                latex += f"\\subsubsection{{{line.strip().lstrip('### ')}}}\n\n"
                
            # Handle lists
            elif line.strip().startswith('- ') or line.strip().startswith('* '):
                if not in_list or list_type != 'itemize':
                    if in_list:
                        latex += f"\\end{{{list_type}}}\n\n"
                    latex += "\\begin{itemize}\n"
                    in_list = True
                    list_type = 'itemize'
                latex += f"\\item {line.strip().lstrip('- ').lstrip('* ')}\n"
                
            elif re.match(r"^\d+\.\s", line.strip()):
                if not in_list or list_type != 'enumerate':
                    if in_list:
                        latex += f"\\end{{{list_type}}}\n\n"
                    latex += "\\begin{enumerate}\n"
                    in_list = True
                    list_type = 'enumerate'
                item_text = re.sub(r'^\d+\.\s', '', line.strip())
                latex += f"\\item {item_text}\n"
                
            # End list if line is not a list item
            elif in_list and line.strip() == '':
                latex += f"\\end{{{list_type}}}\n\n"
                in_list = False
                list_type = None
                
            # Regular text
            elif not in_list:
                # Handle bold and italic formatting
                line = re.sub(r'\*\*(.*?)\*\*', lambda m: "\\textbf{" + m.group(1) + "}", line)
                line = re.sub(r'\*(.*?)\*', lambda m: "\\textit{" + m.group(1) + "}", line)
                
                # Handle inline code
                line = re.sub(r'`(.*?)`', lambda m: "\\texttt{" + m.group(1) + "}", line)
                
                # Add the line
                latex += line + "\n\n"
        
        # Close any open lists
        if in_list:
            latex += f"\\end{{{list_type}}}\n\n"
        
        # Close the document
        latex += "\\end{document}"
        
        return latex
    
    def _markdown_to_html(self, title: str, content: str) -> str:
        """
        Convert Markdown content to HTML format.
        
        Args:
            title: Note title
            content: Markdown content
            
        Returns:
            Content in HTML format
        """
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            max-width: 800px;
            margin: 0 auto;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        code {{
            background-color: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: monospace;
        }}
        pre {{
            background-color: #f5f5f5;
            padding: 16px;
            border-radius: 5px;
            overflow-x: auto;
            font-family: monospace;
        }}
        blockquote {{
            border-left: 4px solid #ddd;
            padding-left: 16px;
            margin-left: 0;
            color: #666;
        }}
        a {{
            color: #0366d6;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        table, th, td {{
            border: 1px solid #ddd;
        }}
        th, td {{
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f5f5f5;
        }}
        img {{
            max-width: 100%;
        }}
    </style>
</head>
<body>
"""
        
        # Process content line by line
        lines = content.split('\n')
        in_list = False
        in_code_block = False
        in_paragraph = False
        list_type = None
        code_language = ""
        
        for line in lines:
            line_content = line.strip()
            
            # Handle code blocks
            if line_content.startswith('```'):
                if not in_code_block:
                    code_language = line_content[3:].strip()
                    html += f'<pre><code class="language-{code_language}">\n'
                    in_code_block = True
                else:
                    html += '</code></pre>\n'
                    in_code_block = False
                continue
            
            if in_code_block:
                # Escape HTML special characters in code blocks
                line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                html += line + '\n'
                continue
            
            # Handle empty lines
            if not line_content:
                if in_paragraph:
                    html += '</p>\n'
                    in_paragraph = False
                if in_list:
                    if list_type == 'ul':
                        html += '</ul>\n'
                    else:
                        html += '</ol>\n'
                    in_list = False
                continue
            
            # Handle headers
            if line_content.startswith('# '):
                html += f'<h1>{line_content[2:]}</h1>\n'
            elif line_content.startswith('## '):
                html += f'<h2>{line_content[3:]}</h2>\n'
            elif line_content.startswith('### '):
                html += f'<h3>{line_content[4:]}</h3>\n'
            elif line_content.startswith('#### '):
                html += f'<h4>{line_content[5:]}</h4>\n'
            elif line_content.startswith('##### '):
                html += f'<h5>{line_content[6:]}</h5>\n'
            elif line_content.startswith('###### '):
                html += f'<h6>{line_content[7:]}</h6>\n'
                
            # Handle lists
            elif line_content.startswith('- ') or line_content.startswith('* '):
                if not in_list or list_type != 'ul':
                    if in_paragraph:
                        html += '</p>\n'
                        in_paragraph = False
                    if in_list:
                        if list_type == 'ol':
                            html += '</ol>\n'
                    else:
                        html += '<ul>\n'
                        in_list = True
                    list_type = 'ul'
                html += f'<li>{line_content[2:]}</li>\n'
                
            elif re.match(r"^\d+\.\s", line_content):
                if not in_list or list_type != 'ol':
                    if in_paragraph:
                        html += '</p>\n'
                        in_paragraph = False
                    if in_list:
                        if list_type == 'ul':
                            html += '</ul>\n'
                    else:
                        html += '<ol>\n'
                        in_list = True
                    list_type = 'ol'
                item_text = re.sub(r"^\d+\.\s", "", line_content)
                html += f'<li>{item_text}</li>\n'
                
            # Regular text (paragraphs)
            else:
                if in_list:
                    if list_type == 'ul':
                        html += '</ul>\n'
                    else:
                        html += '</ol>\n'
                    in_list = False
                
                # Format inline elements
                line_content = self._format_inline_elements(line_content)
                
                if not in_paragraph:
                    html += '<p>'
                    in_paragraph = True
                else:
                    html += ' '
                
                html += line_content
        
        # Close any open tags
        if in_paragraph:
            html += '</p>\n'
        if in_list:
            if list_type == 'ul':
                html += '</ul>\n'
            else:
                html += '</ol>\n'
        
        # Close the HTML document
        html += """
</body>
</html>
"""
        
        return html
    
    def _format_inline_elements(self, text: str) -> str:
        """
        Format inline Markdown elements to HTML.
        
        Args:
            text: Text with Markdown inline formatting
            
        Returns:
            Text with HTML inline formatting
        """
        # Bold
        text = re.sub(r'\*\*(.*?)\*\*', lambda m: f"<strong>{m.group(1)}</strong>", text)
        text = re.sub(r'__(.*?)__', lambda m: f"<strong>{m.group(1)}</strong>", text)
        
        # Italic
        text = re.sub(r'\*(.*?)\*', lambda m: f"<em>{m.group(1)}</em>", text)
        text = re.sub(r'_(.*?)_', lambda m: f"<em>{m.group(1)}</em>", text)
        
        # Code
        text = re.sub(r'`(.*?)`', lambda m: f"<code>{m.group(1)}</code>", text)
        
        # Links
        text = re.sub(r'\[(.*?)\]\((.*?)\)', lambda m: f"<a href=\"{m.group(2)}\">{m.group(1)}</a>", text)
        
        return text
    
    def add_hyperlinks(self, notes: Dict, topics: Dict, output_format: str) -> Dict:
        """
        Add hyperlinks between related topics in the generated notes.
        
        Args:
            notes: Dictionary of generated notes
            topics: Dictionary of extracted topics
            output_format: Output format ('markdown', 'latex', or 'html')
            
        Returns:
            Updated notes dictionary with hyperlinks added
        """
        # For each topic, create hyperlinks to other topics
        for topic_id, topic_data in notes.items():
            content = topic_data['content']
            topic_name = topic_data['name']
            
            # Create links to other topics
            for other_id, other_topic in topics.items():
                if other_id == topic_id:
                    continue  # Skip self-links
                
                other_name = other_topic['name']
                
                # Skip if other topic name is too short (to avoid false positives)
                if len(other_name) < 4:
                    continue
                
                # Create link based on output format
                if output_format.lower() == 'markdown':
                    # Find occurrences of the topic name in content (not already part of a link)
                    pattern = r'(?<!\[)(?<!\]\()' + re.escape(other_name) + r'(?!\])'
                    replacement = f'[{other_name}]({other_name.replace(" ", "_")}.md)'
                    content = re.sub(pattern, replacement, content)
                    
                elif output_format.lower() == 'latex':
                    # For LaTeX, use \hyperref
                    pattern = re.escape(other_name)
                    hyperref_cmd = "\\hyperref"
                    replacement = f'{hyperref_cmd}[{other_name.replace(" ", "_")}]{{{other_name}}}'
                    content = re.sub(pattern, replacement, content)
                    
                elif output_format.lower() == 'html':
                    # For HTML, use <a> tags
                    pattern = r'(?<!</a>)' + re.escape(other_name) + r'(?!<)'
                    replacement = f'<a href="{other_name.replace(" ", "_")}.html">{other_name}</a>'
                    content = re.sub(pattern, replacement, content)
            
            # Update content with hyperlinks
            notes[topic_id]['content'] = content
        
        return notes
