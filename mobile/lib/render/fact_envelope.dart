/// SPEC-17 fact envelope -- the only way a fact reaches a widget.
///
/// Every displayed fact MUST arrive as a FactEnvelope. No bare String values.
/// fromJson throws on missing tier/source (fail-closed).

/// Wire names for FactTier. `assert` is a Dart keyword; member is `assert_`.
enum FactTier {
  assert_,
  hedge,
  ask,
  defer_,
  refuse;

  static FactTier fromWire(String wire) {
    switch (wire) {
      case 'assert':
        return FactTier.assert_;
      case 'hedge':
        return FactTier.hedge;
      case 'ask':
        return FactTier.ask;
      case 'defer':
        return FactTier.defer_;
      case 'refuse':
        return FactTier.refuse;
      default:
        throw ArgumentError('Unknown FactTier wire value: "$wire"');
    }
  }

  String get wire {
    switch (this) {
      case FactTier.assert_:
        return 'assert';
      case FactTier.hedge:
        return 'hedge';
      case FactTier.ask:
        return 'ask';
      case FactTier.defer_:
        return 'defer';
      case FactTier.refuse:
        return 'refuse';
    }
  }
}

/// Immutable envelope. No public constructor accepts a bare String value
/// without tier -- every FactEnvelope requires a tier.
class FactEnvelope {
  final Object? value;
  final String source;
  final double confidence;
  final FactTier tier;
  final DateTime asOf;

  const FactEnvelope({
    required this.value,
    required this.source,
    required this.confidence,
    required this.tier,
    required this.asOf,
  });

  factory FactEnvelope.fromJson(Map<String, dynamic> json) {
    final tierWire = json['tier'];
    if (tierWire == null || tierWire is! String) {
      throw ArgumentError('FactEnvelope.fromJson: missing or invalid "tier"');
    }
    final source = json['source'];
    if (source == null || source is! String || source.isEmpty) {
      throw ArgumentError('FactEnvelope.fromJson: missing or empty "source"');
    }
    return FactEnvelope(
      value: json['value'],
      source: source,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      tier: FactTier.fromWire(tierWire),
      asOf: DateTime.parse(json['as_of'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'value': value,
        'source': source,
        'confidence': confidence,
        'tier': tier.wire,
        'as_of': asOf.toIso8601String().substring(0, 10),
      };
}

/// Typed stub for offline cached place facts (SPEC-22 decision 7).
class CachedPlaceFacts {
  final FactEnvelope? paymentMethods;
  final FactEnvelope? verdict;

  const CachedPlaceFacts({this.paymentMethods, this.verdict});
}
