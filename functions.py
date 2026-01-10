# import sys
# sys.path.insert(0, "python_libs")

import fitz
import numpy as np

from typing import List
from fastapi import UploadFile
import io
from typing import Tuple,Union,Optional
import zipfile
import tempfile
from PIL import Image
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import openpyxl
from pdf2docx import Converter
import os

position_map = {
    "top-left": (0, 100, 200, 100),
    "top-center": (250, 100, 400, 100),
    "top-right": (400, 100, 600, 100),
    "middle-left": (0, 200, 400, 300),
    "middle-center": (250, 400, 400, 300),
    "center": (250, 400, 400, 300),  # Alias for middle-center
    "middle-right": (400, 400, 600, 300),
    "bottom-left": (0, 600, 200, 400),
    "bottom-center": (250, 600, 400, 400),
    "bottom-right": (400, 600, 600, 400),
}

def add_watermark(
    input_pdf_stream: io.BytesIO, 
    watermark_text: str, 
    position: str,
    font_size: int = 48,
    font_name: str = "helv",
    opacity: float = 0.5,
    rotation: int = 0,
    pages: Optional[List[int]] = None,
    bold: bool = False
) -> io.BytesIO:
    """
    Add text watermark to PDF with customization options.
    
    Args:
        input_pdf_stream: Input PDF as BytesIO
        watermark_text: Text to use as watermark
        position: Position on page (e.g., 'middle-center', 'top-left')
        font_size: Font size in points (8-72)
        font_name: Font name (helv, times, courier, etc.)
        opacity: Opacity level (0.0-1.0)
        rotation: Rotation angle in degrees (0, 90, 180, 270)
        pages: List of page numbers (1-indexed) to apply watermark to. None = all pages
        bold: Make text bold
    
    Returns:
        Output PDF as BytesIO
    """
    doc = fitz.open(stream=input_pdf_stream, filetype="pdf")
    
    # Add bold suffix to font name if requested
    if bold:
        font_map = {
            "helv": "hebo",  # Helvetica Bold
            "times": "tibo",  # Times Bold
            "cour": "cobo",  # Courier Bold
        }
        font_name = font_map.get(font_name, font_name)
    
    # Determine which pages to watermark
    if pages is None:
        pages_to_watermark = range(len(doc))
    else:
        # Convert 1-indexed to 0-indexed and filter valid pages
        pages_to_watermark = [p - 1 for p in pages if 0 < p <= len(doc)]
    
    for page_num in pages_to_watermark:
        page = doc.load_page(page_num)
        page_width, page_height = page.rect.width, page.rect.height
        
        # Calculate text dimensions for better positioning
        text_length = len(watermark_text) * font_size * 0.6  # Approximate text width
        text_height = font_size
        
        # Margins from edges
        margin = 50

        # Calculate position based on page dimensions
        position_coords = {
            "top-left": (margin, margin + text_height),
            "top-center": (page_width / 2, margin + text_height),
            "top-right": (page_width - margin, margin + text_height),
            "middle-left": (margin, page_height / 2),
            "middle-center": (page_width / 2, page_height / 2),
            "center": (page_width / 2, page_height / 2),
            "middle-right": (page_width - margin, page_height / 2),
            "bottom-left": (margin, page_height - margin),
            "bottom-center": (page_width / 2, page_height - margin),
            "bottom-right": (page_width - margin, page_height - margin),
        }
        
        pos_x, pos_y = position_coords.get(position, position_coords["middle-center"])
        
        # Use actual opacity with overlay
        # Create a semi-transparent color (gray scale based on opacity)
        color = (0, 0, 0)  # Black text
        
        # Insert text with proper opacity
        page.insert_text(
            (pos_x, pos_y),
            watermark_text,
            fontsize=font_size,
            fontname=font_name,
            rotate=rotation,
            color=color,
            overlay=True,
            opacity=opacity  # This is the correct way to set opacity in PyMuPDF
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
    pages: Optional[List[int]] = None,
    watermark_size: int = 200  # Default watermark size in points
) -> io.BytesIO:
    """
    Add image watermark to PDF with customization options.
    
    Args:
        input_pdf_stream: Input PDF as BytesIO
        watermark_image_stream: Watermark image as BytesIO
        position: Position on page (e.g., 'middle-center', 'top-left')
        opacity: Opacity level (0.0-1.0)
        rotation: Rotation angle in degrees (will be normalized to 0, 90, 180, or 270)
        pages: List of page numbers (1-indexed) to apply watermark to. None = all pages
        watermark_size: Size of watermark in points (default 200)
    
    Returns:
        Output PDF as BytesIO
    """
    doc = fitz.open(stream=input_pdf_stream, filetype="pdf")
    image_data = watermark_image_stream.read()

    # Get image dimensions (to preserve aspect ratio)
    from PIL import Image
    watermark_image_stream.seek(0)
    with Image.open(watermark_image_stream) as img:
        img_width, img_height = img.size
        aspect_ratio = img_width / img_height

    # Normalize rotation to nearest 90-degree increment (PyMuPDF constraint)
    normalized_rotation = int(round(rotation / 90) * 90) % 360
    
    # Determine which pages to watermark
    if pages is None:
        pages_to_watermark = range(len(doc))
    else:
        # Convert 1-indexed to 0-indexed and filter valid pages
        pages_to_watermark = [p - 1 for p in pages if 0 < p <= len(doc)]
    
    for page_num in pages_to_watermark:
        page = doc.load_page(page_num)
        page_width, page_height = page.rect.width, page.rect.height
        
        # Calculate watermark dimensions maintaining aspect ratio
        if aspect_ratio > 1:  # Wider than tall
            wm_width = watermark_size
            wm_height = watermark_size / aspect_ratio
        else:  # Taller than wide
            wm_height = watermark_size
            wm_width = watermark_size * aspect_ratio
        
        # Margins from edges
        margin = 50
        
        # Calculate position based on page dimensions
        position_coords = {
            "top-left": (margin, margin),
            "top-center": ((page_width - wm_width) / 2, margin),
            "top-right": (page_width - wm_width - margin, margin),
            "middle-left": (margin, (page_height - wm_height) / 2),
            "middle-center": ((page_width - wm_width) / 2, (page_height - wm_height) / 2),
            "center": ((page_width - wm_width) / 2, (page_height - wm_height) / 2),
            "middle-right": (page_width - wm_width - margin, (page_height - wm_height) / 2),
            "bottom-left": (margin, page_height - wm_height - margin),
            "bottom-center": ((page_width - wm_width) / 2, page_height - wm_height - margin),
            "bottom-right": (page_width - wm_width - margin, page_height - wm_height - margin),
        }
        
        x0, y0 = position_coords.get(position, position_coords["middle-center"])
        rect = fitz.Rect(x0, y0, x0 + wm_width, y0 + wm_height)
        
        # Insert image as watermark with opacity and rotation
        page.insert_image(
            rect,
            stream=image_data,
            rotate=normalized_rotation,
            overlay=True,
            keep_proportion=True,
            opacity=opacity
        )

    output_pdf_stream = io.BytesIO()
    doc.save(output_pdf_stream)
    doc.close()

    output_pdf_stream.seek(0)
    return output_pdf_stream
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

def image_to_pdf(image_stream: io.BytesIO) -> io.BytesIO:
    try:
        # Open the image using Pillow (supports JPEG, PNG, and other formats)
        image = Image.open(image_stream)
        
        # Convert RGBA/LA to RGB if needed (for PNG with transparency)
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Create a BytesIO buffer to hold the generated PDF
        pdf_stream = io.BytesIO()

        # Create a reportlab canvas to generate the PDF
        c = canvas.Canvas(pdf_stream, pagesize=letter)

        # Get image dimensions and set PDF page size accordingly
        width, height = image.size
        c.setPageSize((width, height))

        # Seek to the beginning of image_stream before drawing
        image_stream.seek(0)
        
        # Use ImageReader to handle BytesIO stream
        image_reader = ImageReader(image_stream)
        c.drawImage(image_reader, 0, 0, width=width, height=height)

        # Save the PDF to the BytesIO buffer
        c.save()

        # Seek to the beginning of the BytesIO buffer to return it
        pdf_stream.seek(0)
        return pdf_stream

    except Exception as e:
        print(f"Error converting image to PDF: {e}")
        raise e


# Keep the old function name for backward compatibility
def jpeg_to_pdf(jpeg_stream: io.BytesIO) -> io.BytesIO:
    """Legacy function - redirects to image_to_pdf"""
    return image_to_pdf(jpeg_stream)
    
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


def split_pdf_by_page_count(file: UploadFile, pages_per_split: int) -> List[io.BytesIO]:
    """
    Split a PDF into multiple files with a specified number of pages each.
    
    Args:
        file: The PDF file to split
        pages_per_split: Number of pages per output file
    
    Returns:
        List of BytesIO objects containing the split PDFs
    """
    pdf_document = fitz.open(stream=file.file.read(), filetype='pdf')
    total_pages = pdf_document.page_count
    split_files = []
    
    # Calculate the number of splits needed
    for start_page in range(0, total_pages, pages_per_split):
        end_page = min(start_page + pages_per_split - 1, total_pages - 1)
        
        # Create a new PDF for this range
        new_pdf = fitz.open()
        new_pdf.insert_pdf(pdf_document, from_page=start_page, to_page=end_page)
        
        # Save to BytesIO
        pdf_bytes = io.BytesIO()
        new_pdf.save(pdf_bytes)
        new_pdf.close()
        pdf_bytes.seek(0)
        
        split_files.append(pdf_bytes)
    
    pdf_document.close()
    return split_files


def split_pdf_by_file_size(file: UploadFile, target_size_mb: float) -> List[io.BytesIO]:
    """
    Split a PDF into multiple files targeting a specific file size.
    
    Args:
        file: The PDF file to split
        target_size_mb: Target size in megabytes for each output file
    
    Returns:
        List of BytesIO objects containing the split PDFs
    """
    pdf_document = fitz.open(stream=file.file.read(), filetype='pdf')
    total_pages = pdf_document.page_count
    split_files = []
    target_size_bytes = target_size_mb * 1024 * 1024
    
    current_pdf = fitz.open()
    current_size = 0
    
    for page_num in range(total_pages):
        # Insert the page into the current PDF
        current_pdf.insert_pdf(pdf_document, from_page=page_num, to_page=page_num)
        
        # Check the current size
        temp_bytes = io.BytesIO()
        current_pdf.save(temp_bytes)
        current_size = temp_bytes.tell()
        
        # If we've exceeded the target size and have at least one page, save this PDF
        if current_size >= target_size_bytes and current_pdf.page_count > 1:
            # Remove the last page that pushed us over
            current_pdf.delete_page(current_pdf.page_count - 1)
            
            # Save the current PDF
            pdf_bytes = io.BytesIO()
            current_pdf.save(pdf_bytes)
            pdf_bytes.seek(0)
            split_files.append(pdf_bytes)
            
            # Start a new PDF with the page that pushed us over
            current_pdf.close()
            current_pdf = fitz.open()
            current_pdf.insert_pdf(pdf_document, from_page=page_num, to_page=page_num)
    
    # Save any remaining pages
    if current_pdf.page_count > 0:
        pdf_bytes = io.BytesIO()
        current_pdf.save(pdf_bytes)
        pdf_bytes.seek(0)
        split_files.append(pdf_bytes)
    
    current_pdf.close()
    pdf_document.close()
    return split_files


def extract_pages_as_separate_files(file: UploadFile, pages: List[int]) -> List[io.BytesIO]:
    """
    Extract specific pages as individual PDF files.
    
    Args:
        file: The PDF file to extract from
        pages: List of page numbers (1-indexed) to extract
    
    Returns:
        List of BytesIO objects, each containing a single page
    """
    pdf_document = fitz.open(stream=file.file.read(), filetype='pdf')
    extracted_files = []
    
    for page_num in pages:
        # Adjust for zero-indexed pages
        page_index = page_num - 1
        
        if 0 <= page_index < pdf_document.page_count:
            # Create a new PDF with just this page
            new_pdf = fitz.open()
            new_pdf.insert_pdf(pdf_document, from_page=page_index, to_page=page_index)
            
            # Save to BytesIO
            pdf_bytes = io.BytesIO()
            new_pdf.save(pdf_bytes)
            new_pdf.close()
            pdf_bytes.seek(0)
            
            extracted_files.append(pdf_bytes)
    
    pdf_document.close()
    return extracted_files


def parse_page_ranges(range_string: str) -> List[Tuple[int, int]]:
    """
    Parse a page range string like "1-5, 10-15, 20" into a list of tuples.
    
    Args:
        range_string: String containing page ranges (e.g., "1-5, 10-15, 20")
    
    Returns:
        List of tuples representing page ranges
    """
    ranges = []
    parts = range_string.split(',')
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            # Range like "1-5"
            start, end = part.split('-')
            ranges.append((int(start), int(end)))
        else:
            # Single page like "20"
            page = int(part)
            ranges.append((page, page))
    
    return ranges


def compress_pdfs_api(
    files: List[UploadFile],
    compression_level: int = 50,
    target_dpi: int = 150
) -> Union[io.BytesIO, List[io.BytesIO]]:
    """
    Compress one or multiple PDF files with advanced options.
    
    Args:
        files: List of PDF files to compress
        compression_level: Compression level from 1-100 (higher = more compression)
        target_dpi: Target DPI for images (72-300)
    
    Returns:
        Compressed PDF(s) as BytesIO object(s)
    """
    
    def compress_pdf(pdf_file: UploadFile) -> io.BytesIO:
        """Compress a single PDF file."""
        pdf_document = fitz.open(stream=pdf_file.file.read(), filetype='pdf')
        print(f"Compressing: {pdf_file.filename} with level {compression_level}, DPI {target_dpi}")
        
        # Map compression level (1-100) to quality settings
        # Higher compression level = lower quality, smaller file
        if compression_level >= 75:  # Maximum compression
            garbage_level = 4
            deflate = True
            image_quality = 50
        elif compression_level >= 50:  # Balanced
            garbage_level = 3
            deflate = True
            image_quality = 75
        else:  # Maximum quality
            garbage_level = 2
            deflate = True
            image_quality = 90
        
        for page in pdf_document:
            # Clean page contents
            page.clean_contents(sanitize=True)
            
            # Compress images on the page
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                try:
                    # Extract image
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Open image with PIL
                    img_pil = Image.open(io.BytesIO(image_bytes))
                    
                    # Resize image based on target DPI if needed
                    # Calculate new size based on DPI ratio
                    current_dpi = img_pil.info.get('dpi', (72, 72))[0]
                    if current_dpi > target_dpi:
                        scale_factor = target_dpi / current_dpi
                        new_size = (int(img_pil.width * scale_factor), int(img_pil.height * scale_factor))
                        img_pil = img_pil.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # Compress image
                    img_buffer = io.BytesIO()
                    if image_ext in ["jpg", "jpeg"]:
                        img_pil.save(img_buffer, format="JPEG", quality=image_quality, optimize=True)
                    elif image_ext == "png":
                        img_pil.save(img_buffer, format="PNG", optimize=True)
                    else:
                        # For other formats, convert to JPEG
                        if img_pil.mode in ("RGBA", "LA", "P"):
                            img_pil = img_pil.convert("RGB")
                        img_pil.save(img_buffer, format="JPEG", quality=image_quality, optimize=True)
                    
                    img_buffer.seek(0)
                    
                    # Replace image in PDF
                    page.replace_image(xref, stream=img_buffer.read())
                except Exception as e:
                    print(f"Error compressing image {img_index} on page: {e}")
                    continue

        # Save the compressed PDF to a BytesIO stream
        compressed_pdf = io.BytesIO()
        pdf_document.save(
            compressed_pdf,
            deflate=deflate,
            garbage=garbage_level,
            clean=True
        )
        pdf_document.close()
        compressed_pdf.seek(0)
        return compressed_pdf

    # Compress all provided PDFs
    compressed_files = [compress_pdf(file) for file in files]
    print(f"Compressed {len(compressed_files)} file(s)")

    # If only one file, return it directly
    if len(compressed_files) == 1:
        return compressed_files[0], '1'

    # If multiple files, zip them together
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for idx, pdf_bytes in enumerate(compressed_files):
            pdf_bytes.seek(0)
            zipf.writestr(f"compressed_{idx + 1}.pdf", pdf_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer, '2'

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


def is_scanned_pdf(pdf_stream: io.BytesIO) -> bool:
    """
    Detect if a PDF is scanned (image-based) by checking for text content.
    
    Args:
        pdf_stream: PDF file as BytesIO
    
    Returns:
        True if PDF appears to be scanned (no text), False otherwise
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        # Check first few pages for text content
        pages_to_check = min(3, doc.page_count)
        total_text_length = 0
        
        for page_num in range(pages_to_check):
            page = doc[page_num]
            text = page.get_text().strip()
            total_text_length += len(text)
        
        doc.close()
        
        # If there's very little text across multiple pages, it's likely scanned
        # Threshold: less than 50 characters across checked pages
        return total_text_length < 50
        
    except Exception as e:
        print(f"Error detecting scanned PDF: {e}")
        return False


def pdf_to_word(pdf_stream: io.BytesIO) -> io.BytesIO:
    """
    Convert PDF to DOCX format with text, image, and table preservation.
    
    Args:
        pdf_stream: PDF file as BytesIO
    
    Returns:
        DOCX file as BytesIO
    """
    try:
        pdf_stream.seek(0)
        
        # Create temporary files for conversion
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_stream.read())
            temp_pdf_path = temp_pdf.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_docx:
            temp_docx_path = temp_docx.name
        
        try:
            # Convert PDF to DOCX using pdf2docx
            cv = Converter(temp_pdf_path)
            cv.convert(temp_docx_path, start=0, end=None)
            cv.close()
            
            # Read the converted DOCX file
            with open(temp_docx_path, 'rb') as docx_file:
                docx_bytes = io.BytesIO(docx_file.read())
            
            docx_bytes.seek(0)
            return docx_bytes
            
        finally:
            # Clean up temporary files
            if os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
            if os.path.exists(temp_docx_path):
                os.unlink(temp_docx_path)
    
    except Exception as e:
        print(f"Error converting PDF to Word: {e}")
        raise e


# ============================================================================
# PASSWORD PROTECTION & UNLOCKING
# ============================================================================

def add_password_to_pdf(
    pdf_stream: io.BytesIO,
    user_password: str,
    owner_password: Optional[str] = None,
    permissions: Optional[int] = None
) -> io.BytesIO:
    """
    Add password protection to a PDF file.
    
    Args:
        pdf_stream: Input PDF as BytesIO
        user_password: Password required to open the PDF
        owner_password: Password for full access (optional, defaults to user_password)
        permissions: Permission flags (optional). Use fitz constants:
                    - PDF_PERM_PRINT: Allow printing
                    - PDF_PERM_MODIFY: Allow modifications
                    - PDF_PERM_COPY: Allow copying text/graphics
                    - PDF_PERM_ANNOTATE: Allow annotations
    
    Returns:
        Password-protected PDF as BytesIO
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        # If no owner password specified, use user password
        if owner_password is None:
            owner_password = user_password
        
        # Default permissions: allow printing and copying, but not modification
        if permissions is None:
            permissions = fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY
        
        # Create output stream
        output_stream = io.BytesIO()
        
        # Save with encryption
        doc.save(
            output_stream,
            encryption=fitz.PDF_ENCRYPT_AES_256,  # Use AES-256 encryption
            user_pw=user_password,
            owner_pw=owner_password,
            permissions=permissions
        )
        doc.close()
        
        output_stream.seek(0)
        return output_stream
        
    except Exception as e:
        print(f"Error adding password to PDF: {e}")
        raise e


def remove_password_from_pdf(
    pdf_stream: io.BytesIO,
    password: str
) -> io.BytesIO:
    """
    Remove password protection from a PDF file.
    
    Args:
        pdf_stream: Input password-protected PDF as BytesIO
        password: Password to unlock the PDF
    
    Returns:
        Unlocked PDF as BytesIO
    
    Raises:
        Exception if password is incorrect
    """
    try:
        pdf_stream.seek(0)
        
        # Try to open with password
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        # Authenticate with password
        if doc.is_encrypted:
            auth_result = doc.authenticate(password)
            if not auth_result:
                raise ValueError("Incorrect password")
        
        # Save without encryption
        output_stream = io.BytesIO()
        doc.save(output_stream, encryption=fitz.PDF_ENCRYPT_NONE)
        doc.close()
        
        output_stream.seek(0)
        return output_stream
        
    except ValueError:
        raise
    except Exception as e:
        print(f"Error removing password from PDF: {e}")
        raise e


# ============================================================================
# PAGE NUMBERING
# ============================================================================

def add_page_numbers(
    pdf_stream: io.BytesIO,
    position: str = "bottom-center",
    format_string: str = "{page}",
    start_page: int = 1,
    skip_first: bool = False,
    font_size: int = 10,
    font_name: str = "helv",
    color: Tuple[float, float, float] = (0, 0, 0)
) -> io.BytesIO:
    """
    Add page numbers to a PDF.
    
    Args:
        pdf_stream: Input PDF as BytesIO
        position: Position on page (top-left, top-center, top-right, 
                 bottom-left, bottom-center, bottom-right)
        format_string: Format for page numbers. Use {page} for current page,
                      {total} for total pages. Examples:
                      - "{page}" -> "1", "2", "3"
                      - "Page {page}" -> "Page 1", "Page 2"
                      - "{page} of {total}" -> "1 of 10", "2 of 10"
                      - "Page {page}/{total}" -> "Page 1/10"
        start_page: Starting page number (default 1)
        skip_first: Skip numbering the first page (useful for cover pages)
        font_size: Font size in points
        font_name: Font name (helv, times, courier)
        color: RGB color tuple (0-1 range for each component)
    
    Returns:
        PDF with page numbers as BytesIO
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        total_pages = doc.page_count
        
        # Position mapping with margins
        margin = 30
        position_coords = {
            "top-left": lambda w, h: (margin, margin),
            "top-center": lambda w, h: (w / 2, margin),
            "top-right": lambda w, h: (w - margin, margin),
            "bottom-left": lambda w, h: (margin, h - margin),
            "bottom-center": lambda w, h: (w / 2, h - margin),
            "bottom-right": lambda w, h: (w - margin, h - margin),
        }
        
        get_position = position_coords.get(position, position_coords["bottom-center"])
        
        for page_num in range(total_pages):
            # Skip first page if requested
            if skip_first and page_num == 0:
                continue
            
            page = doc[page_num]
            page_width = page.rect.width
            page_height = page.rect.height
            
            # Calculate position
            x, y = get_position(page_width, page_height)
            
            # Format the page number text
            current_page = start_page + page_num - (1 if skip_first else 0)
            page_text = format_string.format(page=current_page, total=total_pages)
            
            # Calculate text width for alignment
            text_width = fitz.get_text_length(page_text, fontname=font_name, fontsize=font_size)
            
            # Adjust x position based on alignment
            if "center" in position:
                x = x - (text_width / 2)
            elif "right" in position:
                x = x - text_width
            # For left alignment, x stays as is
            
            # Insert text
            page.insert_text(
                (x, y),
                page_text,
                fontsize=font_size,
                fontname=font_name,
                color=color
            )
        
        # Save the modified PDF
        output_stream = io.BytesIO()
        doc.save(output_stream)
        doc.close()
        
        output_stream.seek(0)
        return output_stream
        
    except Exception as e:
        print(f"Error adding page numbers: {e}")
        raise e


# ============================================================================
# BLANK PAGE REMOVAL
# ============================================================================

def remove_blank_pages(
    pdf_stream: io.BytesIO,
    threshold: float = 0.99
) -> Tuple[io.BytesIO, List[int]]:
    """
    Remove blank or nearly blank pages from a PDF.
    
    Args:
        pdf_stream: Input PDF as BytesIO
        threshold: Whiteness threshold (0-1). Higher values are more strict.
                  0.99 = remove only very blank pages
                  0.95 = remove mostly blank pages
                  0.90 = remove pages with minimal content
    
    Returns:
        Tuple of (cleaned PDF as BytesIO, list of removed page numbers)
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        removed_pages = []
        pages_to_delete = []
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            
            # Check if page is blank using multiple methods
            is_blank = _is_page_blank(page, threshold)
            
            if is_blank:
                removed_pages.append(page_num + 1)  # 1-indexed for user display
                pages_to_delete.append(page_num)
        
        # Delete pages in reverse order to maintain indices
        for page_num in reversed(pages_to_delete):
            doc.delete_page(page_num)
        
        # Save the cleaned PDF
        output_stream = io.BytesIO()
        doc.save(output_stream)
        doc.close()
        
        output_stream.seek(0)
        return output_stream, removed_pages
        
    except Exception as e:
        print(f"Error removing blank pages: {e}")
        raise e


def _is_page_blank(page: fitz.Page, threshold: float = 0.99) -> bool:
    """
    Determine if a page is blank or nearly blank.
    
    Args:
        page: PyMuPDF page object
        threshold: Whiteness threshold (0-1)
    
    Returns:
        True if page is considered blank, False otherwise
    """
    # Method 1: Check for text content
    text = page.get_text().strip()
    if len(text) > 10:  # If there's significant text, not blank
        return False
    
    # Method 2: Check for images
    images = page.get_images()
    if len(images) > 0:  # If there are images, not blank
        return False
    
    # Method 3: Check for drawings/vector graphics
    drawings = page.get_drawings()
    if len(drawings) > 5:  # Allow a few drawings (borders, etc.)
        return False
    
    # Method 4: Render page and check pixel values
    try:
        # Render at low resolution for speed
        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
        
        # Convert to PIL Image for analysis
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Convert to grayscale
        img_gray = img.convert('L')
        
        # Calculate average brightness (0-255)
        import numpy as np
        pixels = np.array(img_gray)
        avg_brightness = pixels.mean() / 255.0
        
        # If average brightness is above threshold, consider it blank
        return avg_brightness >= threshold
        
    except Exception as e:
        print(f"Error analyzing page pixels: {e}")
        # If pixel analysis fails, rely on text/image checks
        return len(text) == 0 and len(images) == 0


def detect_blank_pages(pdf_stream: io.BytesIO, threshold: float = 0.99) -> List[int]:
    """
    Detect blank pages without removing them (for preview).
    
    Args:
        pdf_stream: Input PDF as BytesIO
        threshold: Whiteness threshold (0-1)
    
    Returns:
        List of blank page numbers (1-indexed)
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        blank_pages = []
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            if _is_page_blank(page, threshold):
                blank_pages.append(page_num + 1)  # 1-indexed
        
        doc.close()
        return blank_pages
        
    except Exception as e:
        print(f"Error detecting blank pages: {e}")
        raise e


# ============================================================================
# PDF TO IMAGE CONVERSION
# ============================================================================

def pdf_to_images(
    pdf_stream: io.BytesIO,
    dpi: int = 150,
    image_format: str = "png",
    pages: Optional[List[int]] = None
) -> List[Tuple[io.BytesIO, str]]:
    """
    Convert PDF pages to images.
    
    Args:
        pdf_stream: Input PDF as BytesIO
        dpi: Resolution in DPI (72-300, default 150)
        image_format: Output format - 'png' or 'jpg' (default 'png')
        pages: List of page numbers to convert (1-indexed). None = all pages
    
    Returns:
        List of tuples (image_stream, filename)
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        # Determine which pages to convert
        if pages is None:
            pages_to_convert = range(doc.page_count)
        else:
            # Convert 1-indexed to 0-indexed and filter valid pages
            pages_to_convert = [p - 1 for p in pages if 0 < p <= doc.page_count]
        
        images = []
        
        for page_num in pages_to_convert:
            page = doc[page_num]
            
            # Calculate zoom factor from DPI (default PDF is 72 DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to image bytes
            img_stream = io.BytesIO()
            
            if image_format.lower() == 'jpg' or image_format.lower() == 'jpeg':
                # Convert to JPEG
                img_stream.write(pix.pil_tobytes(format="JPEG", optimize=True, quality=95))
                filename = f"page_{page_num + 1}.jpg"
            else:
                # Convert to PNG (default)
                img_stream.write(pix.pil_tobytes(format="PNG", optimize=True))
                filename = f"page_{page_num + 1}.png"
            
            img_stream.seek(0)
            images.append((img_stream, filename))
        
        doc.close()
        return images
        
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        raise e


# ============================================================================
# FLATTEN PDF
# ============================================================================

def flatten_pdf(pdf_stream: io.BytesIO) -> io.BytesIO:
    """
    Flatten PDF by converting form fields and annotations to static content.
    This prevents further editing and makes the PDF read-only.
    
    Args:
        pdf_stream: Input PDF as BytesIO
    
    Returns:
        Flattened PDF as BytesIO
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            
            # Get all annotations (form fields, comments, etc.)
            annots = page.annots()
            if annots:
                for annot in annots:
                    try:
                        # Get annotation appearance
                        annot.update()
                    except:
                        pass
            
            # Apply redactions (flattens annotations)
            page.apply_redactions()
        
        # Remove form fields by creating a new PDF without them
        output_stream = io.BytesIO()
        doc.save(output_stream, garbage=4, deflate=True, clean=True)
        doc.close()
        
        output_stream.seek(0)
        return output_stream
        
    except Exception as e:
        print(f"Error flattening PDF: {e}")
        raise e


# ============================================================================
# PDF METADATA EDITOR
# ============================================================================

def get_pdf_metadata(pdf_stream: io.BytesIO) -> dict:
    """
    Get PDF metadata information.
    
    Args:
        pdf_stream: Input PDF as BytesIO
    
    Returns:
        Dictionary with metadata
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        metadata = doc.metadata
        
        # Add additional info
        info = {
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "keywords": metadata.get("keywords", ""),
            "creator": metadata.get("creator", ""),
            "producer": metadata.get("producer", ""),
            "creationDate": metadata.get("creationDate", ""),
            "modDate": metadata.get("modDate", ""),
            "page_count": doc.page_count,
            "is_encrypted": doc.is_encrypted,
        }
        
        doc.close()
        return info
        
    except Exception as e:
        print(f"Error getting PDF metadata: {e}")
        raise e


def update_pdf_metadata(
    pdf_stream: io.BytesIO,
    title: Optional[str] = None,
    author: Optional[str] = None,
    subject: Optional[str] = None,
    keywords: Optional[str] = None,
    creator: Optional[str] = None
) -> io.BytesIO:
    """
    Update PDF metadata.
    
    Args:
        pdf_stream: Input PDF as BytesIO
        title: Document title
        author: Document author
        subject: Document subject
        keywords: Document keywords
        creator: Creator application
    
    Returns:
        PDF with updated metadata as BytesIO
    """
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype='pdf')
        
        # Get current metadata
        metadata = doc.metadata.copy()
        
        # Update only provided fields
        if title is not None:
            metadata["title"] = title
        if author is not None:
            metadata["author"] = author
        if subject is not None:
            metadata["subject"] = subject
        if keywords is not None:
            metadata["keywords"] = keywords
        if creator is not None:
            metadata["creator"] = creator
        
        # Set updated metadata
        doc.set_metadata(metadata)
        
        # Save with updated metadata
        output_stream = io.BytesIO()
        doc.save(output_stream, garbage=4, deflate=True)
        doc.close()
        
        output_stream.seek(0)
        return output_stream
        
    except Exception as e:
        print(f"Error updating PDF metadata: {e}")
        raise e

