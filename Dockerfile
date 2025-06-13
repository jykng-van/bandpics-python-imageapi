FROM public.ecr.aws/lambda/python:3.13
# Copy function code
COPY ./app ${LAMBDA_TASK_ROOT}
# Install the function's dependencies using file requirements.txt
# from your project folder.
COPY requirements.txt .
RUN pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" -U --no-cache-dir

# !!! Adding code to python path
ENV PYTHONPATH="$PYTHONPATH:${LAMBDA_TASK_ROOT}"

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}/app

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "main.handler" ]