from PIL import Image, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime
import re

class ImageDataHandler:
    def __init__(self, image:Image.Image):
        #self.image_path = image_path
        self.image = image

    def get_exif_data(self):
        exif_data = self.image.getexif() # get exif data from image
        ifds = ExifTags.IFD._member_names_ # get all the IFD types

        #print(ifds)
        #print(exif_data)

        exif_tags = {}
        if exif_data is not None:
            for k, v in exif_data.items():
                tag = TAGS.get(k,k) # get tag name
                exif_tags[tag] = v # assign value to tag name
                if tag == 'GPSInfo': #check if tag is GPSInfo which is a special case
                    exif_gps = exif_data.get_ifd(ExifTags.IFD.GPSInfo) # get the IFD of that type
                    exif_sub_data = {}
                    for (sk, sv) in exif_gps.items():
                        sub_tag = GPSTAGS.get(sk,sk) # get GPS tag name
                        exif_sub_data[sub_tag] = sv
                    exif_tags[tag] = exif_sub_data # replace the tag name with the IFD data
                elif tag == 'ExifOffset': # check if tag if ExifOffset which is the extra exif data
                    exif_offset = exif_data.get_ifd(ExifTags.IFD.Exif)
                    exif_sub_data = {}
                    for (sk, sv) in exif_offset.items():
                        sub_tag = TAGS.get(sk,sk)
                        exif_sub_data[sub_tag] = sv
                    exif_tags[tag] = exif_sub_data # replace the tag name with the IFD data

            #print(exif_tags)

            return exif_tags

        else:
            return {"error":"No EXIF data found"}

    def get_date_and_coords(self):
        data = {}
        exif_data = self.get_exif_data()

        if "DateTime" in exif_data: # assign DateTime
            data["DateTime"] = self.exif_date_to_dt(exif_data["DateTime"])
        if "ExifOffset" in exif_data: # check if ExifOffset exists
            exif_offset = exif_data["ExifOffset"]
            if "DateTimeOriginal" in exif_offset: # get DateTimeOriginal
                data["DateTimeOriginal"] = self.exif_date_to_dt(exif_offset["DateTimeOriginal"])
            if "OffsetTimeOriginal" in exif_offset: # get OffsetTimeOriginal
                data["OffsetTimeOriginal"] = exif_offset["OffsetTimeOriginal"]

        if "GPSInfo" in exif_data: # if GPSInfo exists
            gps_info = exif_data["GPSInfo"]

            gps_keys = ['GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef'] #GPS keys to check
            if (all(key in gps_info for key in gps_keys)): #check if all keys exist in gps_info
                # convert GPS coordinates to decimal values that can be used by something like Google Maps
                latval = self.convert_degrees_to_decimal(gps_info['GPSLatitude'])
                lat =  latval if gps_info['GPSLatitudeRef'] == 'N' else -latval
                longval = self.convert_degrees_to_decimal(gps_info['GPSLongitude'])
                long = longval if gps_info['GPSLongitudeRef'] == 'E' else -longval

                data["coords"] = {'latitude':lat, 'longitude':long} # assign coordinates to data

        return data

    #convert GPS coordinates which are in degrees, minutes, seconds to decimal degress
    def convert_degrees_to_decimal(self, value):
        d,m,s = value
        return float(d) + float(m)/60.0 + float(s)/3600.0
    #convert exif date string which is YYYY:MM:DD HH:MM:SS to datetime object
    def exif_date_to_dt(self, date_str):
        year,month,day,hour,minute,second = map(int, re.split(r":|\s+", date_str)) #split date string and convert to int
        return datetime(year, month, day, hour, minute, second)
