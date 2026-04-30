API_CONFIG_MAP = {
    "virustotal" : [{
        "file":"processing.conf",
        "section":"virustotal",
        "key":"key"
    },{
        "file":"integrations.conf",
        "section":"virustotal",
        "key":"apikey"
    },],
    "misp" : [{
        "file": "reporting.conf",
        "section":"misp",
        "key":"apikey"
    },{
        "file": "misp.conf",
        "section":"misp",
        "key":"apikey"
    },],
    "mobsf" : [{
        "file": "processing.conf",
        "section":"mobsf",
        "key":"api_key"
    }]
}