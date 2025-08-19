class PriceTrackingException(Exception):
    '''
    Exception used in OSRS and RS3 item price tracking.
    '''

    status: int | None = None
    delay_before_retry: int | None = None

    def __init__(self, message: str, status: int | None = None, delay_before_retry: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.delay_before_retry = delay_before_retry