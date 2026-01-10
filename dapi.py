# import sys
# sys.path.insert(0, "python_libs")

from typing import Union
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import FileResponse, StreamingResponse
import fitz
import os
from functions import *
from functions import is_scanned_pdf, pdf_to_word
from pydantic import BaseModel
from typing import List, Tuple, Optional
import json
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import configuration and validation
from config import config
from validation import validator

# Validate configuration on startup
config.validate()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI()

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Update CORS to use specific origins from config
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Define the email model
class MessageSchema(BaseModel):
    message: str

# Email Configuration from config
SMTP_SERVER = config.SMTP_SERVER
SMTP_PORT = config.SMTP_PORT
SMTP_USER = config.SMTP_USER
SMTP_PASSWORD = config.SMTP_PASSWORD
RECIPIENT_EMAIL = config.RECIPIENT_EMAIL
EMAIL_SUBJECT = config.EMAIL_SUBJECT

@app.post("/send-email")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def send_email(request: Request, data: MessageSchema):
    try:
        # Create the email message
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = RECIPIENT_EMAIL
        msg["Subject"] = EMAIL_SUBJECT
        msg.attach(MIMEText(data.message, "plain"))
        
        # Connect to Gmail's SMTP server using SSL
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, RECIPIENT_EMAIL, msg.as_string())
        
        return {"message": "Email sent successfully!"}
    
    except smtplib.SMTPException as e:
        raise HTTPException(status_code=500, detail=f"SMTP error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")









@app.post("/merge_pdfs")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def merge_pdfs_endpoint(request: Request, files: List[UploadFile] = File(...)):
    try:
        # Validate all files
        for file in files:
            validator.validate_and_sanitize(file)
        
        # Get the merged PDF in memory
        pdf_bytes = merge_pdfs_api(files)
        
        # Generate output filename from first file
        original_name = files[0].filename.rsplit('.', 1)[0] if files else "output"
        output_filename = f"{original_name}Dpdfmerged.pdf"

        # Return the merged PDF as a downloadable file (StreamingResponse)
        return StreamingResponse(
            pdf_bytes,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging PDFs: {str(e)}")
class RangesModel(BaseModel):
    ranges: List[Tuple[int, int]]
    


@app.post("/split_pdfs")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def split_pdfs_endpoint(
    request: Request,
    file: UploadFile = File(...),
    ranges_model: str = Form(...),  # Accepting ranges as a string
):
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Parse the ranges_model JSON string directly
        ranges_data = json.loads(ranges_model)
        
        # Directly extract the ranges from the parsed data
        ranges = ranges_data["ranges"]
        
        # Print received ranges for debugging
        print("Received ranges:", ranges)

        # Get the split PDFs in memory
        split_files = split_pdfs_api(file, ranges)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfsplit.zip"

        # Return the split PDFs as a zip file (StreamingResponse)
        return StreamingResponse(
            zip_files(split_files),
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error splitting PDFs: {str(e)}")


@app.post("/split_by_page_count")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def split_by_page_count_endpoint(
    request: Request,
    file: UploadFile = File(...),
    pages_per_split: int = Form(...)
):
    """
    Split a PDF by page count (e.g., every 10 pages).
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate pages_per_split
        if pages_per_split < 1:
            raise HTTPException(status_code=400, detail="Pages per split must be at least 1")
        
        print(f"Splitting by page count: {pages_per_split} pages per file")
        
        # Split the PDF
        split_files = split_pdf_by_page_count(file, pages_per_split)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfsplit_by_count.zip"
        
        # Return as zip file
        return StreamingResponse(
            zip_files(split_files),
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error splitting PDF by page count: {str(e)}")


@app.post("/split_by_file_size")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def split_by_file_size_endpoint(
    request: Request,
    file: UploadFile = File(...),
    target_size_mb: float = Form(...)
):
    """
    Split a PDF by target file size (e.g., 5MB chunks).
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate target_size_mb
        if target_size_mb <= 0:
            raise HTTPException(status_code=400, detail="Target size must be greater than 0")
        if target_size_mb > 100:
            raise HTTPException(status_code=400, detail="Target size cannot exceed 100MB")
        
        print(f"Splitting by file size: {target_size_mb}MB per file")
        
        # Split the PDF
        split_files = split_pdf_by_file_size(file, target_size_mb)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfsplit_by_size.zip"
        
        # Return as zip file
        return StreamingResponse(
            zip_files(split_files),
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error splitting PDF by file size: {str(e)}")


@app.post("/extract_pages_separate")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def extract_pages_separate_endpoint(
    request: Request,
    file: UploadFile = File(...),
    pages: str = Form(...)
):
    """
    Extract specific pages as individual PDF files.
    Pages can be comma-separated (e.g., "1,3,5") or ranges (e.g., "1-5,10-15").
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        print(f"Extracting pages as separate files: {pages}")
        
        # Parse the page specification
        page_list = []
        if ',' in pages or '-' in pages:
            # Parse ranges
            ranges = parse_page_ranges(pages)
            # Expand ranges into individual pages
            for start, end in ranges:
                page_list.extend(range(start, end + 1))
        else:
            # Single page
            page_list = [int(pages)]
        
        # Extract pages as separate files
        extracted_files = extract_pages_as_separate_files(file, page_list)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfextracted_pages.zip"
        
        # Return as zip file
        return StreamingResponse(
            zip_files(extracted_files),
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error extracting pages: {str(e)}")
    
    
@app.post("/compress")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def compress_pdfs_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),  # Accept multiple files
    compression_level: int = Form(50),     # Compression level 1-100
    target_dpi: int = Form(150),           # Target DPI 72-300
):
    try:
        # Validate all files
        for file in files:
            validator.validate_and_sanitize(file)
        
        # Validate compression level and DPI
        if not 1 <= compression_level <= 100:
            raise HTTPException(status_code=400, detail="Compression level must be between 1 and 100")
        if not 72 <= target_dpi <= 300:
            raise HTTPException(status_code=400, detail="Target DPI must be between 72 and 300")
        
        # Print received parameters for debugging
        print(f"Received compression level: {compression_level}, target DPI: {target_dpi}")

        # Extract files and process compression
        compressed_files, opy = compress_pdfs_api(files, compression_level, target_dpi)

        # If there is only one file, return it directly as a PDF
        if int(opy) == 1:
            print("Compressed file one:", compressed_files)
            original_name = files[0].filename.rsplit('.', 1)[0]
            output_filename = f"{original_name}Dpdfcompressed.pdf"
            return StreamingResponse(
                compressed_files,
                media_type='application/pdf',
                headers={"Content-Disposition": f"attachment; filename={output_filename}"}
            )

        # If there are multiple files, return them as a zip
        else:
            print("Compressed files duplicate:", compressed_files)
            original_name = files[0].filename.rsplit('.', 1)[0]
            output_filename = f"{original_name}Dpdfcompressed.zip"
            
            return StreamingResponse(
                compressed_files,
                media_type='application/zip',
                headers={"Content-Disposition": f"attachment; filename={output_filename}"}
            )

    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error compressing PDFs: {str(e)}")

@app.post("/estimate_compression")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def estimate_compression_endpoint(
    request: Request,
    file: UploadFile = File(...),
    compression_level: int = Form(50),
    target_dpi: int = Form(150),
):
    """
    Estimate the output file size for compression settings.
    Returns original size and estimated compressed size.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate compression level and DPI
        if not 1 <= compression_level <= 100:
            raise HTTPException(status_code=400, detail="Compression level must be between 1 and 100")
        if not 72 <= target_dpi <= 300:
            raise HTTPException(status_code=400, detail="Target DPI must be between 72 and 300")
        
        # Get original file size
        file_content = await file.read()
        original_size = len(file_content)
        
        # Reset file pointer for compression
        await file.seek(0)
        
        # Perform actual compression to get accurate size
        compressed_files, _ = compress_pdfs_api([file], compression_level, target_dpi)
        
        # Get compressed size
        compressed_files.seek(0, 2)  # Seek to end
        compressed_size = compressed_files.tell()
        
        # Calculate compression ratio
        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
        
        return {
            "original_size": original_size,
            "estimated_size": compressed_size,
            "compression_ratio": round(compression_ratio, 2),
            "size_reduction": original_size - compressed_size
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error estimating compression: {str(e)}")

@app.post("/split")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def split_pdf_endpoint(
    request: Request,
    file: UploadFile = File(...),  # Accept a single file
    pages_to_remove: str = Form(...),  # Accept a comma-separated list of page numbers
):
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Print received page numbers for debugging
        print("Received pages to remove:", pages_to_remove)

        # Parse the pages_to_remove into a list of integers
        pages_to_remove_list = [int(page.strip()) - 1 for page in pages_to_remove.split(",")]  # Convert to 0-based indexing

        # Read the uploaded PDF file into memory
        pdf_stream = io.BytesIO(await file.read())

        # Remove the specified pages from the PDF
        modified_pdf = remove_pages_from_pdf(pdf_stream, pages_to_remove_list)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfremoved_pages.pdf"

        # Return the modified PDF as a response
        return StreamingResponse(
            modified_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error splitting PDF: {str(e)}")
    
    
@app.post("/extract")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def extract_pdf_pages_endpoint(
    request: Request,
    file: UploadFile = File(...),
    pages_to_extract: str = Form(...)
):
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        print("Received pages to extract:", pages_to_extract)
        pages_to_extract_list = [int(page.strip()) - 1 for page in pages_to_extract.split(",")]
        pdf_stream = io.BytesIO(await file.read())
        extracted_pdf = extract_pages_from_pdf(pdf_stream, pages_to_extract_list)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfextracted.pdf"

        return StreamingResponse(
            extracted_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error extracting pages from PDF: {str(e)}")
    
    
@app.post("/organize")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def organize_pdf_pages_endpoint(
    request: Request,
    file: UploadFile = File(...),
    pages_to_organize: str = Form(...)
):
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        print("Received pages to organize:", pages_to_organize)
        pages_to_extract_list = [int(page.strip()) - 1 for page in pages_to_organize.split(",")]
        pdf_stream = io.BytesIO(await file.read())
        extracted_pdf = extract_pages_from_pdf(pdf_stream, pages_to_extract_list)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdforganized.pdf"

        return StreamingResponse(
            extracted_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error organizing pages from PDF: {str(e)}")
    
    
@app.post("/repair")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def repair_pdf_endpoint(request: Request, file: UploadFile = File(...)):
    print("in repair............")
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Read the uploaded PDF file into memory
        pdf_stream = io.BytesIO(await file.read())

        # Attempt to repair the PDF
        repaired_pdf = repair_pdf(pdf_stream)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfrepaired.pdf"

        # Return the repaired PDF as a downloadable file
        return StreamingResponse(
            repaired_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error repairing PDF: {str(e)}")
    
    
@app.post("/wordtopdf")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def word_to_pdf_endpoint(request: Request, file: UploadFile = File(...)):
    print("in word to pdf conversion..........")
    try:
        # Validate file (allow Word documents)
        allowed_types = ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
        validator.validate_file_type(file, allowed_types)
        validator.validate_file_size(file)
        
        # Read the uploaded Word file into memory
        word_stream = io.BytesIO(await file.read())

        # Attempt to convert the Word file to PDF
        pdf_stream = convert_word_to_pdf(word_stream)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfword_to_pdf.pdf"

        # Return the converted PDF as a downloadable file
        return StreamingResponse(
            pdf_stream,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error converting Word to PDF: {str(e)}")
    
@app.post("/jpegtopdf")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def jpeg_to_pdf_endpoint(request: Request, file: UploadFile = File(...)):
    try:
        # Validate file (allow JPEG and PNG images)
        allowed_types = ["image/jpeg", "image/png"]
        validator.validate_file_type(file, allowed_types)
        validator.validate_file_size(file)
        
        # Read the uploaded image file as a BytesIO stream
        image_stream = io.BytesIO(await file.read())
        
        # Convert the image to PDF in memory
        pdf_stream = image_to_pdf(image_stream)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfimage_to_pdf.pdf"

        # Return the PDF as a response
        return StreamingResponse(
            pdf_stream, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error converting image to PDF: {str(e)}")


@app.post("/exceltopdf")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def excel_to_pdf_endpoint(request: Request, file: UploadFile = File(...)):
    try:
        # Validate file (allow Excel files)
        allowed_types = ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
        validator.validate_file_type(file, allowed_types)
        validator.validate_file_size(file)
        
        # Read the uploaded Excel file as a BytesIO stream
        excel_stream = io.BytesIO(await file.read())

        # Convert the Excel file to PDF in memory
        pdf_stream = excel_to_pdf(excel_stream)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfexcel_to_pdf.pdf"

        # Return the PDF as a response
        return StreamingResponse(
            pdf_stream, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error converting Excel to PDF: {str(e)}")

@app.post("/rotatepdf")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def rotate_pdf_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    pages: str = Form('')
):
    try:
        # Validate all files
        for file in files:
            validator.validate_and_sanitize(file)
        
        form_data = await request.form()
        # Extract all rotation fields dynamically
        rotations = [int(form_data.get(f'rotation_{i}', 0)) for i in range(len(files))]
        print("Rotations:", rotations)

        pages_to_rotate = [int(page.strip()) - 1 for page in pages.split(',')] if pages else None
        merged_stream = io.BytesIO()

        for idx, file in enumerate(files):
            pdf_stream = io.BytesIO(await file.read())
            pdf_document = fitz.open(stream=pdf_stream, filetype='pdf')
            rotation_angle = rotations[idx]

            if pages_to_rotate:
                for page_num in pages_to_rotate:
                    if page_num < len(pdf_document):
                        pdf_document[page_num].set_rotation(rotation_angle)
            else:
                for page in pdf_document:
                    page.set_rotation(rotation_angle)

            pdf_document.save(merged_stream)

        merged_stream.seek(0)
        
        # Generate output filename
        original_name = files[0].filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfrotated.pdf"
        
        return StreamingResponse(
            merged_stream, 
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error rotating PDF: {str(e)}")

@app.post("/add_watermark")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def add_watermark_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    watermark_text: Optional[str] = Form(None),
    watermark_image: Optional[UploadFile] = File(None),
    position: str = Form('top-left'),
    opacity: float = Form(1.0),
    rotation: float = Form(0.0),
    font_size: int = Form(48),
    font_name: str = Form('helv'),
    bold: bool = Form(False),
    pages: Optional[str] = Form(None)  # Comma-separated page numbers, e.g., "1,3,5"
):
    try:
        # Validate all PDF files
        for file in files:
            validator.validate_and_sanitize(file)
        
        # Validate watermark image if provided
        if watermark_image:
            allowed_types = ["image/jpeg", "image/png"]
            validator.validate_file_type(watermark_image, allowed_types)
            validator.validate_file_size(watermark_image)
        
        # Parse page numbers if provided
        page_list = None
        if pages:
            try:
                page_list = []
                parts = pages.split(',')
                for part in parts:
                    part = part.strip()
                    if '-' in part:
                        # Handle range (e.g., "4-7")
                        start, end = part.split('-')
                        start, end = int(start.strip()), int(end.strip())
                        if start > end:
                            raise HTTPException(status_code=400, detail=f"Invalid range {part}: start must be <= end")
                        page_list.extend(range(start, end + 1))
                    else:
                        # Handle single page
                        page_list.append(int(part))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid page numbers format. Use comma-separated numbers or ranges (e.g., 1,3-5,8)")
        
        merged_stream = io.BytesIO()
        print(position)
        
        # Read watermark image once if provided (to avoid stream position issues)
        watermark_image_data = None
        if watermark_image:
            watermark_image_data = await watermark_image.read()

        for file in files:
            pdf_stream = io.BytesIO(await file.read())
            
            if watermark_image_data:
                # Create a fresh BytesIO for each file to avoid stream position issues
                image_stream = io.BytesIO(watermark_image_data)
                pdf_stream = add_image_watermark(
                    pdf_stream, 
                    image_stream, 
                    position, 
                    opacity, 
                    rotation,
                    pages=page_list
                )
            elif watermark_text:
                pdf_stream = add_watermark(
                    pdf_stream, 
                    watermark_text, 
                    position,
                    font_size=font_size,
                    font_name=font_name,
                    opacity=opacity,
                    rotation=int(rotation),  # Text rotation should be int
                    pages=page_list,
                    bold=bold
                )

            merged_stream.write(pdf_stream.read())

        merged_stream.seek(0)
        
        # Generate output filename
        original_name = files[0].filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfwatermarked.pdf"
        
        return StreamingResponse(
            merged_stream, 
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("Error adding watermark:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error adding watermark: {str(e)}")


@app.post("/pdf_to_word")
# PDF to Word conversion endpoint disabled to reduce deployment size
# @app.post("/pdf_to_word")
# @limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
# async def pdf_to_word_endpoint(request: Request, file: UploadFile = File(...)):
#     """
#     Convert PDF to Word (DOCX) format.
#     Preserves text formatting, images, and table structures.
#     Detects scanned PDFs and notifies user if OCR is required.
#     """
#     print("Converting PDF to Word...")
#     try:
#         # Validate file
#         validator.validate_and_sanitize(file)
#         
#         # Read the uploaded PDF file into memory
#         pdf_stream = io.BytesIO(await file.read())
#         
#         # Check if PDF is scanned
#         if is_scanned_pdf(pdf_stream):
#             raise HTTPException(
#                 status_code=400,
#                 detail="This PDF appears to be scanned or image-based. OCR processing is required for text extraction. Please use the OCR feature first."
#             )
#         
#         # Reset stream position after scanned check
#         pdf_stream.seek(0)
#         
#         # Convert PDF to Word
#         docx_stream = pdf_to_word(pdf_stream)
#         
#         # Generate output filename
#         original_name = file.filename.rsplit('.', 1)[0]
#         output_filename = f"{original_name}Dpdfpdf_to_word.docx"
#         
#         # Return the converted DOCX file
#         return StreamingResponse(
#             docx_stream,
#             media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
#             headers={"Content-Disposition": f"attachment; filename={output_filename}"}
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(e)
#         raise HTTPException(status_code=500, detail=f"Error converting PDF to Word: {str(e)}")



# ============================================================================
# PASSWORD PROTECTION ENDPOINTS
# ============================================================================

class PasswordProtectionRequest(BaseModel):
    user_password: str
    owner_password: Optional[str] = None
    allow_printing: bool = True
    allow_copying: bool = True
    allow_modification: bool = False
    allow_annotation: bool = False

@app.post("/add_password")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def add_password_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user_password: str = Form(...),
    owner_password: Optional[str] = Form(None),
    allow_printing: bool = Form(True),
    allow_copying: bool = Form(True),
    allow_modification: bool = Form(False),
    allow_annotation: bool = Form(False)
):
    """
    Add password protection to a PDF file.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Calculate permissions
        permissions = 0
        if allow_printing:
            permissions |= fitz.PDF_PERM_PRINT
        if allow_copying:
            permissions |= fitz.PDF_PERM_COPY
        if allow_modification:
            permissions |= fitz.PDF_PERM_MODIFY
        if allow_annotation:
            permissions |= fitz.PDF_PERM_ANNOTATE
        
        # Add password
        protected_pdf = add_password_to_pdf(
            pdf_stream,
            user_password,
            owner_password,
            permissions
        )
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfprotected.pdf"
        
        return StreamingResponse(
            protected_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error adding password: {str(e)}")


@app.post("/remove_password")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def remove_password_endpoint(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...)
):
    """
    Remove password protection from a PDF file.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Remove password
        unlocked_pdf = remove_password_from_pdf(pdf_stream, password)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfunlocked.pdf"
        
        return StreamingResponse(
            unlocked_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Incorrect password")
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error removing password: {str(e)}")


# ============================================================================
# PAGE NUMBERING ENDPOINT
# ============================================================================

@app.post("/add_page_numbers")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def add_page_numbers_endpoint(
    request: Request,
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    format_string: str = Form("{page}"),
    start_page: int = Form(1),
    skip_first: bool = Form(False),
    font_size: int = Form(10)
):
    """
    Add page numbers to a PDF.
    
    Position options: top-left, top-center, top-right, bottom-left, bottom-center, bottom-right
    Format examples: "{page}", "Page {page}", "{page} of {total}", "Page {page}/{total}"
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate inputs
        if font_size < 6 or font_size > 72:
            raise HTTPException(status_code=400, detail="Font size must be between 6 and 72")
        
        valid_positions = ["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"]
        if position not in valid_positions:
            raise HTTPException(status_code=400, detail=f"Invalid position. Must be one of: {', '.join(valid_positions)}")
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Add page numbers
        numbered_pdf = add_page_numbers(
            pdf_stream,
            position=position,
            format_string=format_string,
            start_page=start_page,
            skip_first=skip_first,
            font_size=font_size
        )
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfnumbered.pdf"
        
        return StreamingResponse(
            numbered_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error adding page numbers: {str(e)}")


# ============================================================================
# BLANK PAGE REMOVAL ENDPOINTS
# ============================================================================

@app.post("/detect_blank_pages")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def detect_blank_pages_endpoint(
    request: Request,
    file: UploadFile = File(...),
    threshold: float = Form(0.99)
):
    """
    Detect blank pages in a PDF without removing them.
    Returns a list of blank page numbers for preview.
    
    Threshold: 0.90-0.99 (higher = more strict)
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate threshold
        if threshold < 0.5 or threshold > 1.0:
            raise HTTPException(status_code=400, detail="Threshold must be between 0.5 and 1.0")
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Detect blank pages
        blank_pages = detect_blank_pages(pdf_stream, threshold)
        
        return {
            "blank_pages": blank_pages,
            "count": len(blank_pages)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error detecting blank pages: {str(e)}")


@app.post("/remove_blank_pages")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def remove_blank_pages_endpoint(
    request: Request,
    file: UploadFile = File(...),
    threshold: float = Form(0.99)
):
    """
    Remove blank pages from a PDF.
    
    Threshold: 0.90-0.99 (higher = more strict)
    - 0.99 = remove only very blank pages
    - 0.95 = remove mostly blank pages
    - 0.90 = remove pages with minimal content
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate threshold
        if threshold < 0.5 or threshold > 1.0:
            raise HTTPException(status_code=400, detail="Threshold must be between 0.5 and 1.0")
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Remove blank pages
        cleaned_pdf, removed_pages = remove_blank_pages(pdf_stream, threshold)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfcleaned.pdf"
        
        # Return the cleaned PDF with info about removed pages in headers
        return StreamingResponse(
            cleaned_pdf,
            media_type='application/pdf',
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}",
                "X-Removed-Pages": ",".join(map(str, removed_pages)),
                "X-Removed-Count": str(len(removed_pages))
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error removing blank pages: {str(e)}")


# ============================================================================
# PDF TO IMAGE ENDPOINTS
# ============================================================================

@app.post("/pdf_to_images")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def pdf_to_images_endpoint(
    request: Request,
    file: UploadFile = File(...),
    dpi: int = Form(150),
    image_format: str = Form("png"),
    pages: Optional[str] = Form(None)
):
    """
    Convert PDF pages to images (PNG or JPG).
    
    DPI: 72-300 (default 150)
    Format: png or jpg
    Pages: Comma-separated page numbers or ranges (e.g., "1,3-5,8"). Leave empty for all pages.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Validate DPI
        if not 72 <= dpi <= 300:
            raise HTTPException(status_code=400, detail="DPI must be between 72 and 300")
        
        # Validate format
        if image_format.lower() not in ['png', 'jpg', 'jpeg']:
            raise HTTPException(status_code=400, detail="Format must be 'png' or 'jpg'")
        
        # Parse page numbers if provided
        page_list = None
        if pages:
            try:
                page_list = []
                parts = pages.split(',')
                for part in parts:
                    part = part.strip()
                    if '-' in part:
                        start, end = part.split('-')
                        start, end = int(start.strip()), int(end.strip())
                        if start > end:
                            raise HTTPException(status_code=400, detail=f"Invalid range {part}")
                        page_list.extend(range(start, end + 1))
                    else:
                        page_list.append(int(part))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid page numbers format")
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Convert to images
        images = pdf_to_images(pdf_stream, dpi, image_format, page_list)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        
        # If single image, return it directly
        if len(images) == 1:
            img_stream, img_filename = images[0]
            output_filename = f"{original_name}Dpdf{img_filename}"
            ext = 'jpeg' if image_format.lower() in ['jpg', 'jpeg'] else 'png'
            return StreamingResponse(
                img_stream,
                media_type=f'image/{ext}',
                headers={"Content-Disposition": f"attachment; filename={output_filename}"}
            )
        
        # Multiple images - return as zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for img_stream, img_filename in images:
                img_stream.seek(0)
                zipf.writestr(img_filename, img_stream.read())
        
        zip_buffer.seek(0)
        output_filename = f"{original_name}Dpdfimages.zip"
        
        return StreamingResponse(
            zip_buffer,
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error converting PDF to images: {str(e)}")


# ============================================================================
# FLATTEN PDF ENDPOINT
# ============================================================================

@app.post("/flatten_pdf")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def flatten_pdf_endpoint(
    request: Request,
    file: UploadFile = File(...)
):
    """
    Flatten PDF by converting form fields and annotations to static content.
    Makes the PDF read-only and prevents further editing.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Flatten PDF
        flattened_pdf = flatten_pdf(pdf_stream)
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfflattened.pdf"
        
        return StreamingResponse(
            flattened_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error flattening PDF: {str(e)}")


# ============================================================================
# PDF METADATA ENDPOINTS
# ============================================================================

@app.post("/get_pdf_metadata")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def get_pdf_metadata_endpoint(
    request: Request,
    file: UploadFile = File(...)
):
    """
    Get PDF metadata information.
    Returns JSON with title, author, subject, keywords, etc.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Get metadata
        metadata = get_pdf_metadata(pdf_stream)
        
        return metadata
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error getting PDF metadata: {str(e)}")


@app.post("/update_pdf_metadata")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def update_pdf_metadata_endpoint(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    creator: Optional[str] = Form(None)
):
    """
    Update PDF metadata.
    Provide only the fields you want to update.
    """
    try:
        # Validate file
        validator.validate_and_sanitize(file)
        
        # Read PDF
        pdf_stream = io.BytesIO(await file.read())
        
        # Update metadata
        updated_pdf = update_pdf_metadata(
            pdf_stream,
            title=title,
            author=author,
            subject=subject,
            keywords=keywords,
            creator=creator
        )
        
        # Generate output filename
        original_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{original_name}Dpdfmetadata_updated.pdf"
        
        return StreamingResponse(
            updated_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error updating PDF metadata: {str(e)}")

