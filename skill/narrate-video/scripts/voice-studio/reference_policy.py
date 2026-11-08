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


def approval_for(language, config, available):
    """Return the real individual approval or an explicit approved-English grant."""
    reference = reference_code(language, config, available)
    saved = available.get(reference, {}) if isinstance(available, dict) else {}
    current = saved.get('sha256')
    if not current:
        return None
    accepted = config.get('accepted', {})
    individual = accepted.get(language, {})
    if individual.get('engine') == config.get('engine') and individual.get('referenceSha256') == current:
        return {**individual, 'scope': 'language', 'referenceLanguage': reference}
    grant = config.get('sharedEnglishApproval', {})
    english = accepted.get('en', {})
    if reference == 'en' and grant.get('mode') == 'english-reference' and grant.get('engine') == config.get('engine') and grant.get('referenceSha256') == current and grant.get('acceptedEnglishId') and grant.get('acceptedEnglishId') == english.get('id') and english.get('engine') == config.get('engine') and english.get('referenceSha256') == current:
        return {**english, 'scope': 'english-reference', 'referenceLanguage': 'en', 'authorisedAt': grant.get('authorisedAt')}
    return None
