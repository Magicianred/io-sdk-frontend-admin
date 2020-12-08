export const importResponse = {
    "form": [{
      "description": "Import from JSON source. Replace the sample endpoint with your service.",
      "name": "note",
      "type": "message"
    }, {
      "description": "URL",
      "name": "url",
      "required": false,
      "type": "string",
      "value": "http://localhost:3280/api/v1/web/guest/util/sample222"
    }, {
      "description": "Username",
      "name": "username",
      "required": false,
      "type": "string"
    }, {
      "description": "Password",
      "name": "password",
      "required": false,
      "type": "password"
    }, {
      "description": "Args in JSON format to POST:",
      "name": "jsonargs",
      "required": false,
      "type": "textarea",
      "value": "{\"count\":1,\n\"fiscal_code\":\"AAAAAA00A00A000A\",\n\"amount\":0,  \"due_date\":\"\", \"notice_number\":\"\"\n}"
    }, {
      "description": "Use GET (ignoring JSON args):",
      "name": "useget",
      "required": false,
      "type": "checkbox"
    }]
  };

export const importPostResponse = {
    "data": [{
      "amount": 0,
      "fiscal_code": "AAAAAA00A00A000A:1",
      "markdown": "# Benvenuto, AAAAAA00A00A000A:1\nTi diamo il benvenuto. Questo è un messaggio di *benvenuto* per mostrare come generare markdown in **HTML**. Ricordare che deve essere un testo lungo.",
      "subject": "Benvenuto  AAAAAA00A00A000A:1"
    }]
  };