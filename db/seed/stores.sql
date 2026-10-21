-- The stores we track. Safe to run many times: existing stores are not changed.
-- To add a Shopify store, add a row here (or INSERT it by hand) and run: python -m pipeline migrate
INSERT INTO stores (slug, name, base_url) VALUES
    ('fugazee',         'Fugazee',          'https://www.fugazee.com'),
    ('genrage',         'Genrage',          'https://genrage.com'),
    ('nattygarb',       'Natty Garb',       'https://www.nattygarb.com'),
    ('sullitt',         'Sullitt',          'https://sullitt.com'),
    ('warpingtheories', 'Warping Theories', 'https://warpingtheories.com'),
    ('arkar',           'Arkar',            'https://arkar.in'),
    ('noughtone',       'NoughtOne',        'https://www.noughtone.in'),
    ('farak',           'Farak',            'https://www.farak.co'),
    ('offscript',       'Offscript',        'https://offscript.co.in'),
    ('urbanmonkey',     'Urban Monkey',     'https://www.urbanmonkey.com')
ON CONFLICT (slug) DO NOTHING;
