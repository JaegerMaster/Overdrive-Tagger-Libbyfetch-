import os
import requests
from lxml import html
import sys
import json
import re
import unicodedata
import shutil
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TCOM, COMM
from mutagen.mp3 import MP3

def clean_text(text):
    """
    Clean text by removing extra whitespace, normalizing unicode, and handling special characters.
    
    Args:
    text (str): Input text to clean
    
    Returns:
    str: Cleaned text
    """
    if not text:
        return None
    
    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text)
    
    # Remove characters that are not safe for filesystem
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    
    # Remove non-printable characters
    text = re.sub(r'[^\x20-\x7E]', '', text)
    
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', text).strip()
    
    return cleaned if cleaned else "Unknown"

def extract_multiple_elements(elements):
    """
    Extract and clean multiple elements, separating by comma if more than one.
    
    Args:
    elements (list): List of HTML elements
    
    Returns:
    str: Comma-separated cleaned text, or single cleaned text
    """
    # Clean and filter out None values
    cleaned_texts = [
        clean_text(elem.text_content()) 
        for elem in elements 
        if clean_text(elem.text_content())
    ]
    
    # Return None if no texts found
    if not cleaned_texts:
        return None
    
    # If multiple texts, join with comma
    return ', '.join(cleaned_texts) if len(cleaned_texts) > 1 else cleaned_texts[0]

def extract_url_from_filename(filename):
    """
    Extract URL from filename using more flexible methods.
    
    Args:
    filename (str): Name of the MP3 file
    
    Returns:
    str or None: Extracted URL
    """
    # Try splitting by different delimiters
    delimiters = [' - ', '_URL_', '[', '(']
    
    for delimiter in delimiters:
        if delimiter in filename:
            # Split and get the part after the delimiter
            url_part = filename.split(delimiter)[-1].split('.')[0]
            
            # Basic URL validation
            if url_part.startswith('http'):
                return url_part
    
    # If no delimiter works, try to extract URL-like string
    url_match = re.search(r'(https?://[^\s.]+\.[^\s]+)', filename)
    if url_match:
        return url_match.group(1)
    
    return None

def extract_tags_from_url(url, xpath_expressions):
    """
    Extract tags from a given URL using specified XPath expressions.
    
    Args:
    url (str): The URL of the webpage to scrape
    xpath_expressions (list): List of XPath expressions to extract content from
    
    Returns:
    dict: A dictionary with XPath expressions as keys and extracted content as values
    """
    try:
        # Send a GET request to the URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        
        # Raise an exception for bad status codes
        response.raise_for_status()
        
        # Parse the HTML content
        tree = html.fromstring(response.content)
        
        # Extract content for each XPath expression
        results = {}
        for xpath in xpath_expressions:
            # Find all matching elements
            elements = tree.xpath(xpath)
            
            # Clean and process elements
            if elements:
                # Handle anchor tags and multiple elements differently
                if 'a[' in xpath or len(elements) > 1:
                    # For anchor tags or multiple elements, use special extraction
                    results[xpath] = extract_multiple_elements(elements)
                else:
                    # Single element extraction
                    results[xpath] = clean_text(elements[0].text_content())
            else:
                results[xpath] = None
        
        return results
    
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        return None

def update_id3_tags(audio_file_path, extracted_data):
    """
    Update or add ID3 tags for an audio file based on extracted web data.
    
    Args:
    audio_file_path (str): Path to the audio file to update
    extracted_data (dict): Dictionary of extracted web data
    
    Returns:
    dict: Extracted and cleaned tag data
    """
    try:
        # Try to load existing ID3 tags, create if not exists
        try:
            audio = ID3(audio_file_path)
        except:
            # If no ID3 tags exist, create a new ID3 tag
            audio = ID3()
            audio.save(audio_file_path)
            # Reopen the newly created ID3 tags
            audio = ID3(audio_file_path)
        
        # Mapping of XPath to ID3 tag fields
        tag_mapping = {
            '/html/body/main/div[2]/div/div/div[2]/div[1]/h1': {
                'title': TIT2,  # Title
                'album': TALB,  # Album (using the same H1)
            },
            '/html/body/main/div[2]/div/div/div[2]/div[1]/div[1]': TPE1,  # Series/Artist
            '/html/body/main/div[2]/div/div/div[2]/div[1]/div[2]/a[1]': TPE1,  # Additional Artist
            '/html/body/main/div[2]/div/div/div[2]/div[1]/div[2]/a[2]': TCOM,  # Composer
            '//*[@id="title-description"]': COMM  # Description as Comment
        }
        
        # Track extracted and added tags
        extracted_tags = {}
        tags_updated = False
        
        # Use filename as fallback title if no title found
        filename_title = clean_text(os.path.splitext(os.path.basename(audio_file_path))[0])
        
        # Update tags
        for xpath, tag_class in tag_mapping.items():
            if xpath in extracted_data and extracted_data[xpath]:
                # Handle special case for title/album from the same XPath
                if xpath == '/html/body/main/div[2]/div/div/div[2]/div[1]/h1':
                    # Add title tag if not exists
                    if 'TIT2' not in audio:
                        clean_title = clean_text(extracted_data[xpath]) or filename_title
                        audio.add(tag_mapping[xpath]['title'](encoding=3, text=clean_title))
                        extracted_tags['title'] = clean_title
                        tags_updated = True
                    
                    # Add album tag if not exists
                    if 'TALB' not in audio:
                        clean_album = clean_text(extracted_data[xpath]) or "Unknown Album"
                        audio.add(tag_mapping[xpath]['album'](encoding=3, text=clean_album))
                        extracted_tags['album'] = clean_album
                        tags_updated = True
                else:
                    # Check if tag doesn't already exist before adding
                    tag_name = tag_class.__name__ if hasattr(tag_class, '__name__') else str(tag_class)
                    if tag_name not in audio:
                        clean_tag = clean_text(extracted_data[xpath])
                        tag = tag_class(encoding=3, text=clean_tag)
                        audio.add(tag)
                        extracted_tags[tag_name.lower()] = clean_tag
                        tags_updated = True
        
        # If no title was added, use filename as title
        if 'title' not in extracted_tags:
            audio.add(TIT2(encoding=3, text=filename_title))
            extracted_tags['title'] = filename_title
            tags_updated = True
        
        # If no album was added, use "Unknown Album"
        if 'album' not in extracted_tags:
            audio.add(TALB(encoding=3, text="Unknown Album"))
            extracted_tags['album'] = "Unknown Album"
            tags_updated = True
        
        # Save the updated tags if any changes were made
        if tags_updated:
            audio.save(audio_file_path)
            
            print(f"Successfully updated ID3 tags for {audio_file_path}")
            print("Added/Updated tags:")
            for tag, value in extracted_tags.items():
                print(f"{tag.upper()}: {value}")
        
        # Return extracted tags
        return extracted_tags
    
    except Exception as e:
        print(f"Error updating ID3 tags: {e}", file=sys.stderr)
        return {}

def process_mp3_files(base_url):
    """
    Process all MP3 files in the current directory.
    
    Args:
    base_url (str): Base URL to use for scraping tags if not found in filename
    """
    # Ensure tagged files directory exists
    tagged_dir = "tagged_albums"
    os.makedirs(tagged_dir, exist_ok=True)
    
    # XPath expressions to extract
    xpath_expressions = [
        '/html/body/main/div[2]/div/div/div[2]/div[1]/h1',  # Title/Album
        '/html/body/main/div[2]/div/div/div[2]/div[1]/div[1]',  # Series/Artist
        '/html/body/main/div[2]/div/div/div[2]/div[1]/div[2]/a[1]',  # Artist
        '/html/body/main/div[2]/div/div/div[2]/div[1]/div[2]/a[2]',  # Composer
        '//*[@id="title-description"]'  # Description
    ]
    
    # Track number of processed files
    processed_files = 0
    error_files = 0
    skipped_files = 0
    
    # Iterate through all MP3 files in the current directory
    for filename in os.listdir('.'):
        if filename.lower().endswith('.mp3'):
            try:
                # Try to extract URL from filename
                url = extract_url_from_filename(filename)
                
                if not url:
                    # If no URL found, try using base_url
                    if base_url:
                        url = base_url
                    else:
                        print(f"Skipping {filename}: No URL found", file=sys.stderr)
                        skipped_files += 1
                        continue
                
                # Extract tags from URL
                results = extract_tags_from_url(url, xpath_expressions)
                
                if not results:
                    print(f"Failed to extract tags for {filename}", file=sys.stderr)
                    error_files += 1
                    continue
                
                # Update ID3 tags
                extracted_tags = update_id3_tags(filename, results)
                
                # Move file to album-specific folder
                album_name = extracted_tags.get('album', "Unknown Album")
                album_folder = os.path.join(tagged_dir, clean_text(album_name))
                os.makedirs(album_folder, exist_ok=True)
                
                # Create unique filename to prevent overwrites
                base, ext = os.path.splitext(filename)
                new_filename = base
                counter = 1
                while os.path.exists(os.path.join(album_folder, new_filename + ext)):
                    new_filename = f"{base}_{counter}"
                    counter += 1
                
                # Move the file
                shutil.move(filename, os.path.join(album_folder, new_filename + ext))
                print(f"Moved {filename} to {album_folder}")
                
                processed_files += 1
            
            except Exception as e:
                print(f"Error processing {filename}: {e}", file=sys.stderr)
                error_files += 1
    
    # Print summary
    print("\nProcessing Summary:")
    print(f"Total MP3 files processed: {processed_files}")
    print(f"Files with errors: {error_files}")
    print(f"Files skipped (no URL): {skipped_files}")

def main():
    # Default base URL (optional)
    base_url = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Process MP3 files
    process_mp3_files(base_url)

if __name__ == '__main__':
    main()
