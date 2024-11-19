from typing import Union
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import FileResponse, StreamingResponse
import fitz
import os
from functions import *
from pydantic import BaseModel
from typing import List, Tuple,Optional
import json


import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Define the email model
class MessageSchema(BaseModel):
    message: str

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # Use 465 for SSL
SMTP_USER = "rdan99848@gmail.com"
SMTP_PASSWORD = "dqri sluy szoy xcbp"  # Make sure this is an app password
RECIPIENT_EMAIL = "rdan99848@gmail.com"  # Sending back to yourself
EMAIL_SUBJECT = "Pydf Suggestion"

@app.post("/send-email")
async def send_email(data: MessageSchema):
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
async def merge_pdfs_endpoint(files: List[UploadFile] = File(...)):
    try:
        # Get the merged PDF in memory
        pdf_bytes = merge_pdfs_api(files)

        # Return the merged PDF as a downloadable file (StreamingResponse)
        return StreamingResponse(
            pdf_bytes,
            media_type='application/pdf',
            headers={"Content-Disposition": "attachment; filename=merged_output.pdf"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging PDFs: {str(e)}")
class RangesModel(BaseModel):
    ranges: List[Tuple[int, int]]
    


@app.post("/split_pdfs")
async def split_pdfs_endpoint(
    file: UploadFile = File(...),
    ranges_model: str = Form(...),  # Accepting ranges as a string
):
    try:
        # Parse the ranges_model JSON string directly
        ranges_data = json.loads(ranges_model)
        
        # Directly extract the ranges from the parsed data
        ranges = ranges_data["ranges"]
        
        # Print received ranges for debugging
        print("Received ranges:", ranges)

        # Get the split PDFs in memory
        split_files = split_pdfs_api(file, ranges)

        # Return the split PDFs as a zip file (StreamingResponse)
        return StreamingResponse(
            zip_files(split_files),
            media_type='application/zip',
            headers={"Content-Disposition": "attachment; filename=split_output.zip"}
        )

    except Exception as e:

        print(e)
        raise HTTPException(status_code=500, detail=f"Error splitting PDFs: {str(e)}")
    
    
@app.post("/compress")
async def compress_pdfs_endpoint(
    files: list[UploadFile] = File(...),  # Accept multiple files
    compression: str = Form(...),         # Accept compression level
):
    try:
        # Print received compression level for debugging
        print("Received compression level:", compression)

        # Extract files and process compression
        compressed_files,opy = compress_pdfs_api(files, compression)

        # If there is only one file, return it directly as a PDF
        if int(opy) == 1:
            print("Compressed file one:", compressed_files)
            return StreamingResponse(
                compressed_files,
                media_type='application/pdf',
                headers={"Content-Disposition": "attachment; filename=compressed_output.pdf"}
            )

        # If there are multiple files, return them as a zip
        else :
            print("Compressed files duplicate:", compressed_files)
            # Zip the files and return the zip buffer
            
            return StreamingResponse(
                compressed_files,
                media_type='application/zip',
                headers={"Content-Disposition": "attachment; filename=compressed_output.zip"}
            )


    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error compressing PDFs: {str(e)}")

@app.post("/split")
async def split_pdf_endpoint(
    file: UploadFile = File(...),  # Accept a single file
    pages_to_remove: str = Form(...),  # Accept a comma-separated list of page numbers
):
    try:
        # Print received page numbers for debugging
        print("Received pages to remove:", pages_to_remove)

        # Parse the pages_to_remove into a list of integers
        pages_to_remove_list = [int(page.strip()) - 1 for page in pages_to_remove.split(",")]  # Convert to 0-based indexing

        # Read the uploaded PDF file into memory
        pdf_stream = io.BytesIO(await file.read())

        # Remove the specified pages from the PDF
        modified_pdf = remove_pages_from_pdf(pdf_stream, pages_to_remove_list)

        # Return the modified PDF as a response
        return StreamingResponse(
            modified_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": "attachment; filename=modified_output.pdf"}
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error splitting PDF: {str(e)}")
    
    
@app.post("/extract")
async def extract_pdf_pages_endpoint(
    file: UploadFile = File(...),
    pages_to_extract: str = Form(...)
):
    try:
        print("Received pages to extract:", pages_to_extract)
        pages_to_extract_list = [int(page.strip()) - 1 for page in pages_to_extract.split(",")]
        pdf_stream = io.BytesIO(await file.read())
        extracted_pdf = extract_pages_from_pdf(pdf_stream, pages_to_extract_list)

        return StreamingResponse(
            extracted_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": "attachment; filename=extracted_pages.pdf"}
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error extracting pages from PDF: {str(e)}")
    
    
@app.post("/organize")
async def extract_pdf_pages_endpoint(
    file: UploadFile = File(...),
    pages_to_organize: str = Form(...)
):
    try:
        print("Received pages to organize:", pages_to_organize)
        pages_to_extract_list = [int(page.strip()) - 1 for page in pages_to_organize.split(",")]
        pdf_stream = io.BytesIO(await file.read())
        extracted_pdf = extract_pages_from_pdf(pdf_stream, pages_to_extract_list)

        return StreamingResponse(
            extracted_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": "attachment; filename=organized_pages.pdf"}
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error organizing pages from PDF: {str(e)}")
    
    
@app.post("/repair")
async def repair_pdf_endpoint(file: UploadFile = File(...)):
    print("in repair............")
    try:
        # Read the uploaded PDF file into memory
        pdf_stream = io.BytesIO(await file.read())

        # Attempt to repair the PDF
        repaired_pdf = repair_pdf(pdf_stream)

        # Return the repaired PDF as a downloadable file
        return StreamingResponse(
            repaired_pdf,
            media_type='application/pdf',
            headers={"Content-Disposition": "attachment; filename=repaired_output.pdf"}
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error repairing PDF: {str(e)}")
    
    
@app.post("/wordtopdf")
async def word_to_pdf_endpoint(file: UploadFile = File(...)):
    print("in word to pdf conversion..........")
    try:
        # Read the uploaded Word file into memory
        word_stream = io.BytesIO(await file.read())

        # Attempt to convert the Word file to PDF
        pdf_stream = convert_word_to_pdf(word_stream)

        # Return the converted PDF as a downloadable file
        return StreamingResponse(
            pdf_stream,
            media_type='application/pdf',
            headers={"Content-Disposition": "attachment; filename=converted_output.pdf"}
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error converting Word to PDF: {str(e)}")
    
@app.post("/jpegtopdf")
async def jpeg_to_pdf_endpoint(file: UploadFile = File(...)):
    # Read the uploaded JPEG file as a BytesIO stream
    jpeg_stream = io.BytesIO(await file.read())
    
    # Convert the JPEG image to PDF in memory
    pdf_stream = jpeg_to_pdf(jpeg_stream)

    # Return the PDF as a response
    return StreamingResponse(pdf_stream, media_type="application/pdf")


@app.post("/exceltopdf")
async def excel_to_pdf_endpoint(file: UploadFile = File(...)):
    # Read the uploaded Excel file as a BytesIO stream
    excel_stream = io.BytesIO(await file.read())

    # Convert the Excel file to PDF in memory
    pdf_stream = excel_to_pdf(excel_stream)

    # Return the PDF as a response
    return StreamingResponse(pdf_stream, media_type="application/pdf")

@app.post("/rotatepdf")
async def rotate_pdf_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    pages: str = Form('')
):
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
    return StreamingResponse(merged_stream, media_type='application/pdf')

@app.post("/add_watermark")
async def add_watermark_endpoint(
    files: List[UploadFile] = File(...),
    watermark_text: Optional[str] = Form(None),
    watermark_image: Optional[UploadFile] = File(None),
    position: str = Form('top-left'),
    opacity: float = Form(1.0),
    rotation: float = Form(0.0)
):
    merged_stream = io.BytesIO()
    print(position)

    for file in files:
        pdf_stream = io.BytesIO(await file.read())
        
        if watermark_image:
            image_stream = io.BytesIO(await watermark_image.read())
            pdf_stream = add_image_watermark(pdf_stream, image_stream, position, opacity, rotation)
        elif watermark_text:
            pdf_stream = add_watermark(pdf_stream, watermark_text, position)

        merged_stream.write(pdf_stream.read())

    merged_stream.seek(0)
    return StreamingResponse(merged_stream, media_type='application/pdf')