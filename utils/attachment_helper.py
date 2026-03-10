import fitz  # PyMuPDF
import io
import openpyxl


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extracts all text from PDF bytes using PyMuPDF (fitz).
    Handles locked PDFs by returning a warning message.
    """
    text = ""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if doc.is_encrypted:
                return "[LOCKED PDF: cannot extract text]"
            for page in doc:
                text += page.get_text() + "\n"
    except Exception as e:
        return f"[ERROR: PDF extraction failed — {e}]"
    return text.strip()


def extract_text_from_excel(excel_bytes: bytes) -> str:
    """
    Extracts all text from Excel bytes using openpyxl.
    Reads every sheet, every row, every cell.
    Returns readable text representation of all sheets.
    """
    text = ""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            text += f"\n[Sheet: {sheet_name}]\n"
            for row in ws.iter_rows(values_only=True):
                values = [str(cell).strip() for cell in row if cell is not None and str(cell).strip() != ""]
                if values:
                    text += " | ".join(values) + "\n"
    except Exception as e:
        return f"[ERROR: Excel extraction failed — {e}]"
    return text.strip()
