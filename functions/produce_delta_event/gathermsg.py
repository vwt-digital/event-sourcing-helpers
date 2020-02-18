from datetime import datetime, timezone


def gather_publish_msg(msg, columns_publish=None):
    if columns_publish:
        gathered_msg = {}
        for msg_key, value_key in columns_publish.items():
            if type(value_key) is dict and \
                    value_key.get('conversion') == 'geojson_point' and \
                    value_key['longitude_attribute'] in msg and \
                    value_key['latitude_attribute'] in msg:
                gathered_msg[msg_key] = {
                    "type": "Point",
                    "coordinates": [float(msg[value_key['longitude_attribute']]),
                                    float(msg[value_key['latitude_attribute']])]
                }
            elif type(value_key) is dict and \
                    'source_attribute' in value_key and \
                    value_key['source_attribute'] in msg and \
                    msg[value_key['source_attribute']] is not None:
                gathered_msg[msg_key] = msg[value_key['source_attribute']]

                if 'conversion' in value_key:
                    if value_key['conversion'] == 'lowercase':
                        gathered_msg[msg_key] = gathered_msg[
                            msg_key].lower()
                    elif value_key['conversion'] == 'uppercase':
                        gathered_msg[msg_key] = gathered_msg[
                            msg_key].upper()
                    elif value_key['conversion'] == 'capitalize':
                        gathered_msg[msg_key] = \
                            gathered_msg[msg_key].capitalize()
                    elif value_key['conversion'] == 'datetime':
                        if isinstance(gathered_msg[msg_key], int):
                            # the datetime was converted by Pandas to Unix epoch in milliseconds
                            date_object = datetime.fromtimestamp(int(gathered_msg[msg_key] / 1000), timezone.utc)
                        else:
                            date_object = datetime.strptime(
                                gathered_msg[msg_key], value_key.get(
                                    'format_from', '%Y-%m-%dT%H:%M:%SZ'))
                        gathered_msg[msg_key] = str(
                            datetime.strftime(date_object, value_key.get(
                                'format_to', '%Y-%m-%dT%H:%M:%SZ')))
                if 'prefix_value' in value_key:
                    gathered_msg[msg_key] = f"{value_key['prefix_value']}{gathered_msg[msg_key]}"
            elif type(value_key) is not dict and value_key in msg and \
                    msg[value_key] is not None:
                gathered_msg[msg_key] = msg[value_key]
            else:
                gathered_msg[msg_key] = None
        return gathered_msg
    return msg