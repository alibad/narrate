"""Resolve saved user references without writing profile or audition state."""


def reference_code(language, config, available, requested=None):
    explicit = requested or config.get('references', {}).get(language)
    if explicit:
        return explicit
    if language in available:
        return language
    if 'en' in available:
        return 'en'
    return None


def effective_references(config, available):
    return {language: reference_code(language, config, available)
            for language in config['languages']}
