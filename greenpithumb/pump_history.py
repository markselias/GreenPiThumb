def last_pump_time(watering_event_store):
    """Returns the time of the most recent pump watering event.

    Args:
        watering_event_store: Database store from which to retrieve watering
            event history.

    Returns:
        Timestamp of most recent pump watering event, as a datetime.
    """
    watering_history = watering_event_store.get()
    if len(list(watering_history)) == 0:
        return None
    watering_history_list = list(watering_history)
    watering_history_list.sort(key=lambda record: record.timestamp)
    return watering_history_list[-1].timestamp
