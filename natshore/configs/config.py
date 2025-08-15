import yaml
from collections import namedtuple

def convert(
    file_dir  : str  = None,
    dictionary: dict = None
    ) -> namedtuple:
    
    if file_dir is not None:
        assert file_dir.endswith("yaml"), "the file should be .yaml format"
        
        with open(file_dir, "r") as f:
            dictionary = yaml.full_load(f)
            
    if dictionary is not None:
        for k in dictionary.keys():
            if isinstance(dictionary[k], dict):
                dictionary[k] = convert(dictionary=dictionary[k])
        return namedtuple("GenericDict", dictionary.keys())(**dictionary)
