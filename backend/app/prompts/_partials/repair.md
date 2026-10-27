{% if issues %}

### FIX FROM PREVIOUS ATTEMPT
Your previous attempt failed backend validation. Return the complete result again and fix these problems:
{% for issue in issues %}
- {{ issue }}
{% endfor %}
{% endif %}
