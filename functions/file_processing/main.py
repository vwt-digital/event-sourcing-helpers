import json
import config
import logging
import traceback
import io
import hashlib
import pandas as pd
import unicodedata
from google.cloud import storage

logging.basicConfig(level=logging.INFO)
client = storage.Client()


def send_bytestream_to_filestore(bytesIO, filename, bucket_name):
    bucket = client.get_bucket(bucket_name)
    blob = storage.Blob(filename, bucket)
    if filename.endswith('.xlsx'):
        blob.upload_from_string(
            bytesIO.getvalue(),
            content_type=config.MEDIA_TYPE
        )
    else:
        blob.upload_from_string(
            bytesIO,
            content_type=config.MEDIA_TYPE
        )
    logging.info('Write file {} to {}'.format(filename, bucket_name))


def remove_file_from_filestore(bucket_name, filename):
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(filename)
    blob.delete()
    logging.info('Deleted file {} from {}'.format(filename, bucket_name))


def preprocessing(bucket_name, blob_name):
    logging.info('Preprocess start')
    df = df_from_store(bucket_name, blob_name)

    # Check if contains the correct columns
    cols_exp = set(list(config.COLUMN_MAPPING.keys()))
    cols_present = set(list(df))

    if cols_exp.difference(cols_present):
        missing = cols_exp - cols_present
        message = 'The uploaded file does not contain the correct columns.' + \
            ' The following columns are missing: "{}".'.format(
                '", "'.join(list(missing)))

        logging.info(message)
        return dict(
            status='failure',
            message=message
        )

    # Check if contains data
    if len(df) == 0:
        message = 'The uploaded file does not contain content'
        logging.info(message)
        return dict(
            status='warning',
            message=message
        )

    # rename the columns
    df = df.rename(columns=config.COLUMN_MAPPING)

    # remove characters from certain columns
    if hasattr(config, 'REMOVE_CHAR_FROM_COLUMN'):
        for key, value in config.REMOVE_CHAR_FROM_COLUMN.items():
            df[key] = df[key].str[0:-value].str.strip()

    # normalize string columns
    if hasattr(config, 'COLUMNS_NORMALIZE'):
        for col in config.COLUMNS_NORMALIZE:
            df[col] = df[col].apply(lambda x: unicodedata.normalize('NFKD', x))

    # combine columns
    if hasattr(config, 'COLUMN_COMBINE'):
        for key, value in config.COLUMN_COMBINE.items():
            df[key] = df[value].apply(lambda x: '_'.join(x.dropna().astype(str)), axis=1)

    # Columns to be hashed
    if hasattr(config, 'COLUMNS_HASH'):
        for col in config.COLUMNS_HASH:
            df[col] = df[col].apply(lambda x: hashlib.sha256(x.encode()).hexdigest())

    # replace '' with none values
    for col in df.columns:
        df.at[df[col] == '', col] = None

    # Only keep non-PII columns
    df = df[config.COLUMNS_NONPII]

    # Return file as byte-stream
    if blob_name.endswith('.xlsx'):
        bytesIO = io.BytesIO()
        excel_writer = pd.ExcelWriter(bytesIO, engine="xlsxwriter")
        df.to_excel(excel_writer, sheet_name="data", index=False)
        excel_writer.save()
    else:
        if hasattr(config, 'JSON_ELEMENTS'):
            df = df.to_dict(orient='records')
            bytesIO = {config.JSON_ELEMENTS[-1]: df}
            bytesIO = json.dumps(bytesIO).encode('utf-8')
        else:
            df = df.to_json()
            bytesIO = json.dumps(df).encode('utf-8')

    return dict(
        status='success',
        message='file succesfully processed',
        file=bytesIO
    )


def df_from_store(bucket_name, blob_name):
    path = 'gs://{}/{}'.format(bucket_name, blob_name)
    if blob_name.endswith('.xlsx'):
        df = pd.read_excel(path, dtype=str)
    elif blob_name.endswith('.json'):
        if hasattr(config, 'JSON_ELEMENTS'):
            json_elements = getattr(config, 'JSON_ELEMENTS', [])
            bucket = storage.Client().get_bucket(bucket_name)
            blob = storage.Blob(blob_name, bucket)
            content = blob.download_as_string()
            data = json.loads(content.decode('utf-8'))
            for el in json_elements:
                data = data[el]
            df = pd.DataFrame.from_records(data)
        else:
            df = pd.read_json(path, dtype=False)
    else:
        raise ValueError('File is not json or xlsx: {}'.format(blob_name))
    logging.info('Read file {} from {}'.format(blob_name, bucket_name))
    return df


def file_processing(data, context):
    logging.info('Run started')
    bucket_name = data['bucket']
    filename = data['name']

    if hasattr(config, 'FILEPATH_PREFIX_FILTER'):
        if not filename.startswith(config.FILEPATH_PREFIX_FILTER):
            logging.info('File not in filepath_prefix filter. Skip preprocessing')
            return dict(
                stutus='succes',
                message='file is skipped'
            )

    try:
        # Read dataframe from store
        preprocessed = preprocessing(bucket_name, filename)

        send_bytestream_to_filestore(preprocessed['file'], filename, config.INBOX)
        delete = config.DELETE if hasattr(config, 'DELETE') else True
        if delete:
            remove_file_from_filestore(bucket_name, filename)

        logging.info('Processing file {} successful'.format(filename))
    except Exception:
        logging.error('Processing file {} failed!'.format(filename))
        traceback.print_exc()
