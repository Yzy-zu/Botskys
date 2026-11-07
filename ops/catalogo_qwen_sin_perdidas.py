"""Prototipo local reversible: catálogo completo con schemas compartidos, sin selección previa."""
import json
from botsky.frontend.catalog import Catalog

COLUMNS=('action_key','operation','description','references','availability','permission','effect','confirmation','attachment','constants','parameters')

class LosslessCatalog(Catalog):
    def describe(self):
        source=super().describe();schemas={};lookup={};rows=[]
        for entry in source:
            row=dict(entry);parameters=dict(row['parameters']);properties={}
            for name,schema in parameters['properties'].items():
                canonical=json.dumps(schema,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                if canonical not in lookup:
                    key='s'+str(len(lookup));lookup[canonical]=key;schemas[key]=schema
                properties[name]=lookup[canonical]
            parameters['properties']=properties;row['parameters']=parameters
            rows.append([row[key] for key in COLUMNS])
        return {'encoding':'Cada fila de actions es UNA acción directa completa. Sus valores siguen columns. En parameters.properties cada valor es la clave de su schema completo en field_schemas; expandirlo conceptualmente. No son subherramientas ni una segunda selección. Conserva restricciones y descripciones exactas.',
                'columns':list(COLUMNS),'field_schemas':schemas,'actions':rows}


def expand(encoded):
    result=[]
    for row in encoded['actions']:
        entry=dict(zip(encoded['columns'],row,strict=True));parameters=dict(entry['parameters'])
        parameters['properties']={name:encoded['field_schemas'][key] for name,key in parameters['properties'].items()}
        entry['parameters']=parameters;result.append(entry)
    return result
