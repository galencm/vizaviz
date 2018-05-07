start redis with keyspace notifications enabled:
```
redis-server redis.conf
```

start a vizaviz server:
```
python3 vizaviz.py --server-name foo --source-dir ../bar
```

start a gui:
```
python3 vizaviz_gui.py
```

start a gui with args (the extra -- is needed so that args are not captured by kivy)
```
python3 vizaviz_gui.py -- --focus-name bar
```