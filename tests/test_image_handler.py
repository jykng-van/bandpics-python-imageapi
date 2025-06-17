import unittest
from unittest.mock import patch, MagicMock
from PIL import Image, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime
import piexif
import io
#from collections.abc import MutableMapping

from app.image_data_handler import ImageDataHandler # We're testing the ImageDataHandler class

class test_image_handler(unittest.TestCase):

    # Mocking exif data and ifd data to simulate the behavior of the ImageDataHandler class
    class mock_exif():
        def __init__(self, data, ifds):
            self._data = data # Mock exif data, which is a dictionary
            self._ifds = ifds # Mock ifd data, which is a dictionary with keys as ifd types and values as dictionaries

        def items(self):
            return self._data.items() # Mock items so that it returns _data items

        def get_ifd(self, ifd): # Mock get_idf so that it returns the ifd data
            return self._ifds.get(ifd, {})

    def setUp(self):
        self.img = MagicMock() # Mock img object
        self.testdate = datetime(2025,1,1,0,0,0) # Test date to reuse
        self.testexifdate = '2025:01:01 00:00:00' # Test exif date to reuse
        self.testgpsdegrees = (12,34,56)

        # Mocking the image exif data and it's ifd data
        self.img.getexif.return_value = self.mock_exif({
            0x0132: self.testexifdate, # DateTime
            0x8825: 0x0001, # GPSInfo
            0x8769: 0x0002, # ExifOffset
        },
        {
            ExifTags.IFD.GPSInfo:{ # Mock GPSInfo data
                0x0001: 'N', # GPSLatitudeRef
                0x0002: self.testgpsdegrees,# GPSLatitude
                0x0003: 'W', # GPSLongitudeRef
                0x0004: self.testgpsdegrees # GPSLongitude
            },
            ExifTags.IFD.Exif: { # Mock ExifOffset data
                0x9003: self.testexifdate, # DateTimeOriginal
                0x9011: '+00:00' # OffsetTimeOriginal
            }
        })

    # Test get_exif_data to ensure that tags are extracted as expected
    def test_get_exif_data(self):
        handler = ImageDataHandler(self.img)
        results = handler.get_exif_data()
        # Check if the results match
        assert results['DateTime'] == self.testexifdate, "DateTime does not match"
        assert results['GPSInfo']['GPSLatitudeRef'] == 'N', "GPSLatitudeRef not found"
        assert results['ExifOffset']['DateTimeOriginal'] == self.testexifdate, "DateTimeOriginal does not match"

    # Test convert_to_degrees to ensure that the GPS coordinates are converted correctly
    def test_convert_degrees_to_decimal(self):
        degrees = (45, 67, 89) # Mock GPS coordinates in degrees, minutes, seconds format
        decimal = float(degrees[0]) + float(degrees[1]) / 60.0 + float(degrees[2]) / 3600.0
        handler = ImageDataHandler(self.img)
        assert handler.convert_degrees_to_decimal(degrees) == decimal, "Degrees conversion failed"

    # Test if exif date is converted to datetime object correctly
    def test_exif_date_to_dt(self):
        handler = ImageDataHandler(self.img)
        dt = handler.exif_date_to_dt(self.testexifdate)
        assert dt == self.testdate, "Date conversion failed"

    # Test get_date_and_coords to ensure that date information and coords are set
    def test_get_date_and_coords(self):
        handler = ImageDataHandler(self.img)
        results = handler.get_date_and_coords()
        testcoord = self.testgpsdegrees[0] + float(self.testgpsdegrees[1]) / 60.0 +  float(self.testgpsdegrees[2]) / 3600.0

        # check if results match
        assert results['DateTime'] == self.testdate, "DateTime does not match"
        assert results['DateTimeOriginal'] == self.testdate, "DateTimeOriginal does not match"
        assert results['coords']['latitude'] == testcoord and results['coords']['longitude'] -testcoord, "Coordinates do not match"

    def create_test_image(self, width=100, height=100, color='red', gps_data={}):
        image = Image.new('RGB', (width, height), color=color)
        stream = io.BytesIO()
        exif_dict = {"0th":{}, "Exif":{}, "GPS":gps_data, "1st":{}, "thumbnail":None}
        exif_bytes = piexif.dump(exif_dict)
        image.save(stream, format='JPEG', exif=exif_bytes)
        stream.seek(0)
        return stream

    #test remove_gps
    def test_remove_gps(self):
        handler = ImageDataHandler(self.img)
        gps_ifd = {
            piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
            piexif.GPSIFD.GPSLatitudeRef: 'N',
            piexif.GPSIFD.GPSLatitude: [(123, 1), (45,1), (500000, 10000)],
            piexif.GPSIFD.GPSLongitudeRef: 'W',
            piexif.GPSIFD.GPSLongitude: [(123, 1), (45,1), (500000, 10000)],
        }
        image_data = self.create_test_image(width=4048, height=3036, gps_data=gps_ifd) # create test image with GPS

        # now check if test image has GPS
        image = Image.open(image_data)
        exif_data = piexif.load(image.info.get('exif',''))
        assert 'GPS' in exif_data, "Test image doesn't have GPS"

        new_exif = handler.remove_gps(image) # do remove_gps
        print('new_exif', new_exif)
        stream = io.BytesIO()
        image.save(stream, format='JPEG', exif=new_exif)
        stream.seek(0)
        mod_image = Image.open(stream)
        mod_data = piexif.load(mod_image.info.get('exif',{}))
        print(mod_data)

        assert 'GPS' not in mod_data or not mod_data['GPS'], "Modified image still has non-empty GPS data"
