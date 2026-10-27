{% if method == "function_calling" %}
Your response MUST call {{ output_name }} exactly once. Do not return JSON as final text. Put the result in the tool arguments, which follow the shape below.
{% else %}
Return exactly one JSON object matching this schema. Do not use markdown fences or explanations.
{{ schema_json }}
Use one outer object containing only the listed top-level properties. Do not nest the complete object inside another object.
{% endif %}
Return only the requested structure. A declared tool only formats the response and is never executed; do not request any other tool or external action.
