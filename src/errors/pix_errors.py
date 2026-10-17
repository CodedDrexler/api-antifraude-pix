class PixError(Exception):
    def __init__(self, code: str, description: str):
        self.code = code
        self.description = description
        super().__init__(description)


class AnalysisNotFound(PixError):
    def __init__(self):
        super().__init__("PIX000404", "Pix transaction analysis not found")


class TransactionConflict(PixError):
    def __init__(self):
        super().__init__("PIX000409", "Transaction ID already exists with a different payload")
