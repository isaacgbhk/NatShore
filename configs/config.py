import yaml
from collections import namedtuple

def convert(
    file_dir  : str  = None,
    dictionary: dict = None
    ) -> namedtuple:
    
    if file_dir is not None:
        if not file_dir.endswith("yaml"):
            raise ValueError(f"Config file must be a .yaml file, got: {file_dir}")
        
        with open(file_dir, "r") as f:
            dictionary = yaml.full_load(f)
            
    if dictionary is not None:
        for k in dictionary.keys():
            if isinstance(dictionary[k], dict):
                dictionary[k] = convert(dictionary=dictionary[k])
        return namedtuple("GenericDict", dictionary.keys())(**dictionary)
