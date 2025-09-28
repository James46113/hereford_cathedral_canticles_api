import requests
from bs4 import BeautifulSoup
import os
import fitz  # pymupdf
from datetime import datetime, timedelta
import json


class Service:
    def __init__(self, date, canticles, composer, type):
        self.date = date
        self.canticles = canticles
        self.composer = composer
        self.type = type

    def __str__(self):
        return f"{self.date} {self.type}: {self.canticles} - {self.composer}"


def get_datetime_from_date_range(date_range):
    split_date = []
    if " - " in date_range:
        split_date = date_range.split(" - ")
    else:
        split_date = date_range.split(" – ")
    start_date = ""
    if len(split_date[0]) <= 2:
        start_date = split_date[0] + " " + " ".join(split_date[1].split(" ")[1:])
    else:
        start_date = split_date[0] + " " + split_date[1][-4:]
    return datetime.strptime(start_date, "%d %B %Y")

page = requests.get("https://www.herefordcathedral.org/music-lists")
soup = BeautifulSoup(page.text, "html.parser")
download_link_elements = soup.find_all(class_="downloadLink")
download_link_elements = [link for link in download_link_elements if link.get_text(strip=True) != '']
download_links = [('https://www.herefordcathedral.org' + link['href'], link.get_text(strip=True)) for link in download_link_elements if link.has_attr('href')]


def extract_text_with_formatting(page):
    """Extract text with formatting information from a PDF page"""
    blocks = page.get_text("dict")
    
    for block in blocks["blocks"]:
        if "lines" in block:
            for line in block["lines"]:
                line_text = ""
                italic_text = ""
                bold_text = ""
                
                for span in line["spans"]:
                    text = span["text"]
                    flags = span["flags"]
                    
                    # Flag 2 indicates italic text
                    is_italic = bool(flags & 2)  # bit 1 is italic
                    # Flag 16 indicates bold text
                    is_bold = bool(flags & 16)  # bit 4 is bold
                    
                    line_text += text
                    if is_italic and text.strip():
                        italic_text += text
                    if is_bold and text.strip():
                        bold_text += text
                
                if line_text.strip():
                    yield line_text.strip(), italic_text.strip(), bold_text.strip()

def clean_spaced_text(text):
    return text.replace("  ", " ")

def load_canticles() -> list[Service]:
    os.makedirs("pdfs", exist_ok=True)
    for ind, link in enumerate(download_links):
        filename = os.path.join("pdfs", link[0].split("/")[-1])
        response = requests.get(link[0])
        if response.status_code == 200:
            with open(f"pdfs/{link[1]}.pdf", "wb") as f:
                f.write(response.content)

    services = []
    morning_found = False
    evening_found = False

    for pdf_file in os.listdir("pdfs"):
        if pdf_file.lower().endswith(".pdf"):
            file_path = os.path.join("pdfs", pdf_file)
            date_index = 0
            start_date = get_datetime_from_date_range(file_path[5:][:-4])
            
            doc = fitz.open(file_path)
            for page in doc:
                # Extract text with formatting information
                formatted_lines = list(extract_text_with_formatting(page))
                
                for ind, (line, italic_text, bold_text) in enumerate(formatted_lines):

                    service_date = start_date + timedelta(days=date_index)
                    is_sunday = service_date.weekday() == 6  # Sunday is 6

                    if "Evensong" in bold_text.replace(" ", ""):
                        for i in range(1, 10):
                            if ind + i < len(formatted_lines):
                                next_line, next_italic_text, next_bold_text = formatted_lines[ind + i]
                                if "service" in next_line.lower().replace(" ", ""):
                                    services.append(Service(service_date + timedelta(seconds=2), clean_spaced_text(next_line.strip()).replace(" "+next_italic_text, ""), next_italic_text, "Evensong"))
                                    break
                        else:
                            canticles = ""
                            for i in range(1, 10):
                                if ind + i < len(formatted_lines):
                                    next_line, next_italic_text, next_bold_text = formatted_lines[ind + i]
                                    if "magnificat" in next_line.lower().replace(" ", ""):
                                        canticles += clean_spaced_text(next_line.strip()) + ", "
                                        services.append(Service(service_date if is_sunday else service_date + timedelta(seconds=2), clean_spaced_text(next_line.strip()).replace(" "+next_italic_text, ""), next_italic_text, "Evensong"))
                                    elif "nuncdimittis" in next_line.lower().replace(" ", ""):
                                        services.append(Service(service_date + timedelta(seconds=3), clean_spaced_text(next_line.strip()).replace(" "+next_italic_text, ""), next_italic_text, "Evensong"))
                                        break

                        if not is_sunday:
                            date_index += 1
                        else:
                            evening_found = True
                    elif "EveningPrayer" in bold_text.strip().replace(" ", ""):
                        if not is_sunday:
                            date_index += 1
                        else:
                            evening_found = True

                    elif "Matins" in bold_text.replace(" ", ""):
                        for i in range(1, 10):
                            if ind + i < len(formatted_lines):
                                next_line, next_italic_text, next_bold_text = formatted_lines[ind + i]
                                if "service" in next_line.lower().replace(" ", ""):
                                    services.append(Service(service_date, clean_spaced_text(next_line.strip()).replace(" "+next_italic_text, ""), next_italic_text, "Matins"))
                                    break
                        else:
                            canticles = ""
                            for i in range(1, 10):
                                if ind + i < len(formatted_lines):
                                    next_line, next_italic_text, next_bold_text = formatted_lines[ind + i]
                                    if "tedeum" in next_line.lower().replace(" ", ""):
                                        canticles += clean_spaced_text(next_line.strip()) + ", "
                                        services.append(Service(service_date, clean_spaced_text(next_line.strip()).replace(" "+next_italic_text, ""), next_italic_text, "Matins"))
                                    elif "jubilate" in next_line.lower().replace(" ", ""):
                                        services.append(Service(service_date + timedelta(seconds=1), clean_spaced_text(next_line.strip()).replace(" "+next_italic_text, ""), next_italic_text, "Matins"))
                                        break
                        morning_found = True
                    
                    elif "MorningPrayer" in bold_text.strip().replace(" ", ""):
                        morning_found = True

                    if is_sunday and morning_found and evening_found:
                            date_index += 1
                            morning_found = False
                            evening_found = False
            
            doc.close()


    # Remove duplicates where all attributes are the same
    unique_services = []
    seen = set()
    for s in services:
        key = (s.date, s.canticles, s.composer, s.type)
        if key not in seen:
            seen.add(key)
            unique_services.append(s)
    services = unique_services
    services.sort(key=lambda x: x.date)

    services = [service for service in services if service.date > datetime.now() - timedelta(days=1)]

    return services


if __name__ == "__main__":
    canticles_list = [
        {
            "date": canticles.date.isoformat(),
            "canticles": canticles.canticles,
            "composer": canticles.composer,
            "type": canticles.type
        }
        for canticles in load_canticles()
    ]
    with open("canticles.json", "w") as f:
        f.write(json.dumps(canticles_list, indent=2))