from abc import ABC, abstractmethod
import pandas as pd

class ParserBase(ABC):
    def __init__(self, file_path):
        self.file_path = file_path

    @abstractmethod
    def list_all_fields(self) -> dict:
        pass

    @abstractmethod
    def get_custom_dataframe(self, field_mapping: dict) -> pd.DataFrame:
        pass
