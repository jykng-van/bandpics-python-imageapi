# Bandpics: Image API (Python version)
This is an API for the Bandpics project, it primarily deals with images including extracting their Exif data related to locations and time, and managing the images themselves.

The Python version (I might eventually make a Node.js version) uses FastAPI, Pydantic, MongoDB and Pillow so far.

## How it's structured
There's 2 collections in the MongoDB dataase:
- `images`: Which contains some metadata about the images, including their filename, GPS coordinates, time they were taken, and the image group they belong to.
- `image_groups`: Which represents a group of images, and includes a name and description. They'll eventually be associated with an event.

## The API
The API endpoints are CRUD endpoints for images and image groups. I'll write some more about them later.

## Things done
- Added a basic FastAPI app with CRUD endpoints for images and image groups.
- Added schemas for images and image groups using Pydantic.
- Added a class image_handler for extracting the Exif data from images.
- Added unit tests for image_handler and integrations tests for the API endpoints.

## To Do
- Integrate S3 for storing the images.
- Possibly adding logging depending on where it's deployed.
- Possibly making it AWS Lambda compatible.
- Possbily having methods to remove GPS data from images if needed.