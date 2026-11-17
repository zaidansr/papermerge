"""Curated subject shortcuts, not an official Cambridge popularity ranking."""
TOP_SUBJECTS = {
    'IGCSE': ('0580','0606','0500','0510','0610','0620','0625','0450','0455','0452',
              '0478','0417','0460','0470','0475','0520','0530','0654','0457','0400'),
    'AS & A Level': ('9709','9231','9700','9701','9702','9609','9708','9706','9608','9626',
                     '9093','9695','9990','9699','9489','9696','9084','9479','9239','9395'),
}
SUBJECT_HINTS = {'0606': 'Additional Mathematics', '0607': 'International Mathematics',
                 '0500': 'English — First Language', '0510': 'English — Second Language',
                 '0475': 'Literature in English', '9231': 'Further Mathematics',
                 '9093': 'English Language', '9608': 'Computer Science (archived syllabus)'}

SESSION_PRESETS = {'All sessions': {'m','s','w'}, 'February / March': {'m'},
                   'May / June': {'s'}, 'October / November': {'w'}}
TYPE_PRESETS = {'Question papers': {'qp'}, 'Questions + answers': {'qp','ms'},
                'Mark schemes only': {'ms'}, 'Inserts only': {'in'},
                'Examiner reports': {'er'}, 'Grade thresholds': {'gt'},
                'Instructions': {'ci'}, 'All document types': {'qp','ms','in','er','gt','ci'}}
