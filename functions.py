import fitz
from typing import List
from fastapi import UploadFile
import io
from typing import Tuple,Union,Optional
import zipfile
import pypandoc
import tempfile
from PIL import Image
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import openpyxl

position_map = {
    "top-left": (0, 100, 200, 100),
    "top-center": (250, 100, 400, 100),
    "top-right": (400, 100, 600, 100),
    "middle-left": (0, 200, 400, 300),
    "middle-center": (250, 400, 400, 300),
    "middle-right": (400, 400, 600, 300),
    "bottom-left": (0, 600, 200, 400),
    "bottom-center": (250, 600, 400, 400),
    "bottom-right": (400, 600, 600, 400),
}

def add_watermark(input_pdf_stream: io.BytesIO, watermark_text: str, position: str) -> io.BytesIO:
    doc = fitz.open(stream=input_pdf_stream, filetype="pdf")
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        page_width, page_height = page.rect.width, page.rect.height

        # Get position coordinates for the watermark
        if position == "center":
            pos_x = (page_width - 200) / 2  # Adjust as needed
            pos_y = (page_height - 50) / 2  # Adjust as needed
        else:
            pos = position_map.get(position, position_map["top-left"])
            pos_x = pos[0] if pos[0] >= 0 else page_width + pos[0] - 200
            pos_y = pos[1] if pos[1] >= 0 else page_height + pos[1] - 50
        
        # Add the watermark text directly to the page
        text = watermark_text
        font_size = 48
        color = (0.5, 0.5, 0.5)  # Gray color

        page.insert_text(
            (pos_x, pos_y),
            text,
            fontsize=font_size,
            fontname="helv",
            rotate=0,
            color=color
        )

    output_pdf_stream = io.BytesIO()
    doc.save(output_pdf_stream)
    doc.close()

    output_pdf_stream.seek(0)
    return output_pdf_stream

def add_image_watermark(
    input_pdf_stream: io.BytesIO,
    watermark_image_stream: io.BytesIO,
    position: str,
    opacity: float = 1.0,
    rotation: float = 0.0,
    increment: int = 20  # Value to adjust position by
) -> io.BytesIO:
    doc = fitz.open(stream=input_pdf_stream, filetype="pdf")
    image_data = watermark_image_stream.read()

    # Get image dimensions (to preserve aspect ratio)
    from PIL import Image
    with Image.open(watermark_image_stream) as img:
        img_width, img_height = img.size

    position_map = {
        "top-left": (0, 100, 200, 100),
        "top-center": (250, 100, 400, 100),
        "top-right": (400, 100, 600, 100),
        "middle-left": (0, 200, 400, 300),
        "middle-center": (250, 400, 400, 300),
        "middle-right": (400, 400, 600, 300),
        "bottom-left": (0, 600, 200, 400),
        "bottom-center": (250, 600, 400, 400),
        "bottom-right": (400, 600, 600, 400),
    }
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        # Get initial position coordinates for the image watermark
        pos = position_map.get(position, position_map["top-left"])
        print("Initial Position:", pos)  # Debug print to check the position
        rect = fitz.Rect(pos[0], pos[1], pos[2], pos[3])

        # Get page size
        page_width, page_height = page.rect.width, page.rect.height

        # Check if the rectangle is valid (within bounds and non-zero size)
        while rect.width <= 0 or rect.height <= 0 or rect.x1 > page_width or rect.y1 > page_height:
            print(f"Invalid rectangle at position '{position}', adjusting...")

            # Increment the position by 'increment' (e.g., 20px) to shift it
            pos = (pos[0] + increment, pos[1] + increment, pos[2] + increment, pos[3] + increment)

            # Recreate the rect with updated position
            rect = fitz.Rect(pos[0], pos[1], pos[2], pos[3])

            # Ensure the rect is within page bounds and has a reasonable size
            rect = fitz.Rect(
                max(0, rect.x0), 
                max(0, rect.y0), 
                min(page_width, rect.x1), 
                min(page_height, rect.y1)
            )

            # Ensure the rect has a reasonable size (using image dimensions)
            if rect.width <= 0 or rect.height <= 0:
                # Keep the aspect ratio of the image
                aspect_ratio = img_width / img_height
                min_size = 50  # Set a reasonable minimum size for the watermark

                # Calculate new size while maintaining aspect ratio
                if rect.width <= 0:
                    rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + min_size, rect.y0 + min_size / aspect_ratio)
                if rect.height <= 0:
                    rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + min_size * aspect_ratio, rect.y0 + min_size)

            # Print debug information
            print(f"Adjusted Position: {pos}, New Rect: {rect}")

            # If it's still invalid after multiple adjustments, skip the page or fallback
            if rect.width <= 0 or rect.height <= 0:
                print(f"Skipping page {page_num} due to invalid rectangle after adjustments.")
                break

        # Insert image as watermark with optional opacity and rotation
        page.insert_image(
            rect,
            stream=image_data,
            rotate=rotation,
            overlay=True,
            keep_proportion=True,
        )

    output_pdf_stream = io.BytesIO()
    doc.save(output_pdf_stream)
    doc.close()

    output_pdf_stream.seek(0)
    return output_pdf_stream



def excel_to_pdf(excel_stream: io.BytesIO) -> io.BytesIO:
    try:
        # Load the Excel file using openpyxl
        excel_stream.seek(0)
        workbook = openpyxl.load_workbook(excel_stream)
        sheet = workbook.active

        # Create a BytesIO buffer for the output PDF
        pdf_stream = io.BytesIO()
        c = canvas.Canvas(pdf_stream, pagesize=letter)

        # Get the width and height of a PDF page
        page_width, page_height = letter

        # Set starting coordinates
        x_offset = 50
        y_offset = page_height - 50
        line_height = 15

        # Write each row from the Excel sheet into the PDF
        for row in sheet.iter_rows(values_only=True):
            row_text = " | ".join([str(cell) if cell is not None else "" for cell in row])

            # Check if the text fits on the current page, else add a new page
            if y_offset < 50:
                c.showPage()
                c.setFont("Helvetica", 10)
                y_offset = page_height - 50

            c.drawString(x_offset, y_offset, row_text)
            y_offset -= line_height

        # Save the PDF document
        c.save()

        # Reset the stream position to the beginning
        pdf_stream.seek(0)
        return pdf_stream

    except Exception as e:
        print(f"Error converting Excel to PDF: {e}")
        raise e

def jpeg_to_pdf(jpeg_stream: io.BytesIO) -> io.BytesIO:
    try:
        # Open the JPEG image using Pillow
        image = Image.open(jpeg_stream)
        
        # Create a BytesIO buffer to hold the generated PDF
        pdf_stream = io.BytesIO()

        # Create a reportlab canvas to generate the PDF
        c = canvas.Canvas(pdf_stream, pagesize=letter)

        # Get image dimensions and set PDF page size accordingly
        width, height = image.size
        c.setPageSize((width, height))

        # Seek to the beginning of jpeg_stream before drawing
        jpeg_stream.seek(0)
        
        # Use ImageReader to handle BytesIO stream
        image_reader = ImageReader(jpeg_stream)
        c.drawImage(image_reader, 0, 0, width=width, height=height)

        # Save the PDF to the BytesIO buffer
        c.save()

        # Seek to the beginning of the BytesIO buffer to return it
        pdf_stream.seek(0)
        return pdf_stream

    except Exception as e:
        print(f"Error converting JPEG to PDF: {e}")
        raise e
    
def convert_word_to_pdf(word_stream: io.BytesIO) -> io.BytesIO:
    try:
        # Read the Word document content using python-docx
        word_doc = Document(word_stream)
        
        # Create a BytesIO buffer to hold the generated PDF
        pdf_stream = io.BytesIO()
        
        # Create a reportlab canvas to generate the PDF
        c = canvas.Canvas(pdf_stream, pagesize=letter)
        
        # Set up a starting Y position for the text (top of the page)
        y_position = 750
        
        # Loop through paragraphs in the Word document and add them to the PDF
        for para in word_doc.paragraphs:
            c.drawString(72, y_position, para.text)  # 72 is a margin from the left
            y_position -= 14  # Move down for the next line

            # If text is too long and exceeds the page, add a new page
            if y_position < 72:
                c.showPage()  # Start a new page
                y_position = 750  # Reset the Y position for the new page
        
        # Save the PDF to the BytesIO buffer
        c.save()

        # Seek to the beginning of the BytesIO buffer to return it
        pdf_stream.seek(0)
        return pdf_stream

    except Exception as e:
        print(f"Error converting Word to PDF: {e}")
        raise e

def merge_pdfs_api(files: List[UploadFile]):
    # Create a new PDF document to hold the merged content
    merged_pdf = fitz.open()

    # Loop through the input files
    for file in files:
        # Read the content of each uploaded file
        pdf = fitz.open(stream=file.file.read(), filetype='pdf')
        # Insert the entire PDF into the merged document
        merged_pdf.insert_pdf(pdf)
        # Close the current PDF file
        pdf.close()

    # Save the merged PDF to a BytesIO object (in-memory)
    pdf_bytes = io.BytesIO()
    merged_pdf.save(pdf_bytes)
    merged_pdf.close()

    # Seek to the beginning of the in-memory PDF before returning it
    pdf_bytes.seek(0)
    return pdf_bytes

def zip_files(files: List[io.BytesIO]) -> io.BytesIO:
    # Create a BytesIO object to hold the zip content
    zip_bytes = io.BytesIO()

    # Use zipfile to compress the files
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for idx, pdf_bytes in enumerate(files):
            # Write each PDF as a separate file in the zip archive
            pdf_bytes.seek(0)  # Ensure we're reading from the start
            zipf.writestr(f"split_{idx + 1}.pdf", pdf_bytes.read())

    # Move the cursor to the beginning of the BytesIO object
    zip_bytes.seek(0)
    return zip_bytes

def rotate_pdf_api(file: UploadFile, rotation_angle: int, page_numbers: Optional[List[int]] = None) -> io.BytesIO:
    # Read the uploaded PDF file as a BytesIO stream
    pdf_stream = io.BytesIO(file.file.read())
    
    # Open the PDF with PyMuPDF
    pdf_document = fitz.open(stream=pdf_stream, filetype='pdf')
    
    # Rotate specified pages or all pages if `page_numbers` is None
    if page_numbers is None:
        # Rotate all pages
        for page in pdf_document:
            page.set_rotation(rotation_angle)
    else:
        # Rotate only specified pages
        for page_num in page_numbers:
            if 0 <= page_num < len(pdf_document):
                pdf_document[page_num].set_rotation(rotation_angle)
    
    # Save the rotated PDF to a BytesIO object (in memory)
    rotated_pdf_stream = io.BytesIO()
    pdf_document.save(rotated_pdf_stream)
    pdf_document.close()
    
    # Move the stream position back to the start
    rotated_pdf_stream.seek(0)
    return rotated_pdf_stream

def split_pdfs_api(file: UploadFile, ranges: List[Tuple[int, int]]):
    # Open the uploaded PDF file in memory
    pdf_document = fitz.open(stream=file.file.read(), filetype='pdf')
    split_files = []

    # Loop through the provided page ranges
    for idx, (start, end) in enumerate(ranges):
        # Create a new PDF for each range
        new_pdf = fitz.open()
        
        # Adjust for zero-indexed pages in PyMuPDF
        new_pdf.insert_pdf(pdf_document, from_page=start - 1, to_page=end - 1)
        
        # Save the split PDF to a BytesIO object (in-memory)
        pdf_bytes = io.BytesIO()
        new_pdf.save(pdf_bytes)
        new_pdf.close()
        
        # Seek to the beginning of the in-memory PDF
        pdf_bytes.seek(0)
        
        # Append the in-memory file to the list
        split_files.append(pdf_bytes)

    # Close the original PDF document
    pdf_document.close()
    return split_files


def compress_pdfs_api(
    files: List[UploadFile],
    compress_images: bool = True,
    dpi: int = 96,
    quality: int = 85
) -> Union[io.BytesIO, List[io.BytesIO]]:
    """Compress one or multiple PDF files."""
    
    def compress_pdf(pdf_file: UploadFile) -> io.BytesIO:
        """Compress a single PDF file."""
        pdf_document = fitz.open(stream=pdf_file.file.read(), filetype='pdf')
        print("Compressing:", pdf_file.filename)
        for page in pdf_document:
            # Compress images on each page
            if compress_images:
                page.clean_contents(sanitize=True)

        # Save the compressed PDF to a BytesIO stream
        compressed_pdf = io.BytesIO()
        pdf_document.save(compressed_pdf, deflate=True, garbage=4)
        pdf_document.close()
        compressed_pdf.seek(0)
        return compressed_pdf

    # Compress all provided PDFs
    compressed_files = [compress_pdf(file) for file in files]
    print(len(compressed_files))

    # If only one file, return it directly
    if len(compressed_files) == 1:
        return compressed_files[0],'1'

    # If multiple files, zip them together
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for idx, pdf_bytes in enumerate(compressed_files):
            pdf_bytes.seek(0)
            zipf.writestr(f"compressed_{idx + 1}.pdf", pdf_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer,'2'

def remove_pages_from_pdf(pdf_stream: io.BytesIO, pages_to_remove: List[int]) -> io.BytesIO:
    # Open the PDF file from the in-memory stream
    pdf_document = fitz.open(stream=pdf_stream, filetype='pdf')

    # Sort pages in reverse order to avoid shifting indices when deleting
    pages_to_remove.sort(reverse=True)

    # Remove specified pages
    for page_num in pages_to_remove:
        pdf_document.delete_page(page_num)

    # Create a new in-memory buffer for the modified PDF
    modified_pdf_stream = io.BytesIO()
    pdf_document.save(modified_pdf_stream)
    modified_pdf_stream.seek(0)  # Go back to the beginning of the stream

    return modified_pdf_stream

def extract_pages_from_pdf(pdf_stream: io.BytesIO, pages_to_extract: List[int]) -> io.BytesIO:
    # Open the PDF file from the in-memory stream
    pdf_document = fitz.open(stream=pdf_stream, filetype='pdf')

    # Create a new PDF to save the extracted pages
    extracted_pdf = fitz.open()

    # Add only the specified pages to the new PDF
    for page_num in pages_to_extract:
        if 0 <= page_num < pdf_document.page_count:
            extracted_pdf.insert_pdf(pdf_document, from_page=page_num, to_page=page_num)

    # Save the extracted pages to a BytesIO object (in-memory)
    pdf_bytes = io.BytesIO()
    extracted_pdf.save(pdf_bytes)
    pdf_document.close()
    extracted_pdf.close()

    # Seek to the beginning of the in-memory PDF before returning it
    pdf_bytes.seek(0)
    return pdf_bytes

def repair_pdf(pdf_stream: io.BytesIO) -> io.BytesIO:
    try:
        # Open the corrupted PDF from the in-memory stream
        pdf_document = fitz.open(stream=pdf_stream, filetype='pdf')
        
        # Save the repaired PDF to a new in-memory stream
        repaired_pdf_bytes = io.BytesIO()
        pdf_document.save(repaired_pdf_bytes)
        pdf_document.close()
        
        # Seek to the beginning of the in-memory PDF before returning it
        repaired_pdf_bytes.seek(0)
        return repaired_pdf_bytes
    except Exception as e:
        print(f"Error repairing PDF: {e}")
        raise e
    
# def convert_word_to_pdf(word_stream: io.BytesIO) -> io.BytesIO:
#     try:
#         # Create a temporary file to store the uploaded Word file
#         with tempfile.NamedTemporaryFile(delete=False, mode="wb") as temp_word_file:
#             temp_word_file.write(word_stream.read())
#             temp_word_file.close()

#             # Convert the Word file to PDF
#             output_pdf_path = f"{temp_word_file.name}.pdf"
#             pypandoc.convert_file(temp_word_file.name, 'pdf', outputfile=output_pdf_path)

#             # Read the converted PDF file into memory
#             with open(output_pdf_path, "rb") as pdf_file:
#                 pdf_bytes = io.BytesIO(pdf_file.read())
            
#             # Return the PDF as an in-memory byte stream
#             pdf_bytes.seek(0)
#             return pdf_bytes
#     except Exception as e:
#         print(f"Error converting Word to PDF: {e}")
#         raise e
