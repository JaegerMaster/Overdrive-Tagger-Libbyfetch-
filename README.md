# Overdrive-Tagger-Libbyfetch-
Tags the files obtained from Overdrive through Libbyfetch

1. Obtain the Audiobook by using Libbyfetch (https://github.com/jdalbey/libbyfetch)

2. Install the required dependecies:
3. 
    `pip install mutagen`
   
    `pip install json`
   
    `pip install lxml`

4. Go to the Overdrive page of the Audiobook: `https://library.overdrive.com/media/mediaid` and copy the URL

5. Run `python3 OD_tagger_V2.py <URL>`

It will tag the files with: 

  Album
 
  Author
  
  Narrator
  
  Description

And move the tagged files in a seperate folder under `./tagged_albums`
