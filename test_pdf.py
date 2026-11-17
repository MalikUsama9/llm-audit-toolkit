from weasyprint import HTML

html = """
<html>
  <head>
    <style>
      body { font-family: sans-serif; padding: 40px; }
      h1 { color: #1a4d8f; }
      table { border-collapse: collapse; width: 100%; }
      td, th { border: 1px solid #999; padding: 6px; }
    </style>
  </head>
  <body>
    <h1>Hello World: Audit Report Test</h1>
    <p>If you can read this in a PDF, WeasyPrint works.</p>
    <table>
      <tr><th>Category</th><th>Score</th></tr>
      <tr><td>Factual</td><td>20 of 25</td></tr>
    </table>
  </body>
</html>
"""

HTML(string=html).write_pdf("test.pdf")
print("Done: test.pdf created")