FROM public.ecr.aws/lambda/python:3.13

# Copy requirements file
COPY ./requirements.txt ${LAMBDA_TASK_ROOT}

# Install dependencies
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --no-cache-dir

# Copy function code
COPY ./app ${LAMBDA_TASK_ROOT}/app/

# !!! Adding code to python path
ENV PYTHONPATH="$PYTHONPATH:${LAMBDA_TASK_ROOT}"

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}/app

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "main.handler" ]