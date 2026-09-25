/// Closed-list friendly labels for SPEC-08 micro_location storage keys.
///
/// Unknown keys return null -- the caller should omit the line rather
/// than show the raw slug.  Never title-case an unknown key as a
/// generic fallback (that still leaks the internal key).

/// Returns a human-readable neighbourhood label for a micro_location
/// key, or null if the key is not in the closed map.
String? friendlyMicroLocation(String? key) {
  if (key == null) return null;
  return _labels[key];
}

const _labels = <String, String>{
  // -- Laos: Vientiane --
  'nam_phou_fountain': 'Nam Phou Fountain area',
  'patuxai_district': 'Patuxai district',
  'chanthabouly_riverfront': 'Chanthabouly riverfront',
  'sisattanak_embassy_zone': 'Sisattanak embassy zone',
  'vat_chan_waterfront': 'Vat Chan waterfront',
  // -- Laos: Vang Vieng --
  'town_centre_riverfront': 'Town centre, riverfront',
  'nam_xong_west_bank': 'Nam Xong west bank',
  // -- Laos: Luang Prabang --
  'peninsula_old_town': 'Peninsula old town',
  'nam_khan_riverfront': 'Nam Khan riverfront',
  'phousi_central': 'Phousi central',
  'ban_khemkhong': 'Ban Khemkhong',
  // -- Dubai --
  'Downtown': 'Downtown Dubai',
  'Jumeirah': 'Jumeirah',
  'Dubai Marina': 'Dubai Marina',
  'JBR': 'JBR',
  'DIFC': 'DIFC',
  'Deira': 'Deira',
  'Business Bay': 'Business Bay',
  'Al Quoz': 'Al Quoz',
  'D3': 'Dubai Design District',
};
