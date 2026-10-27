/// SPEC-43 Gap 5: production open of the offline store.
///
/// Web and the default stub open unencrypted. On dart:io platforms,
/// Android and iOS open with SQLCipher; desktop stays unencrypted.
export 'offline_open_stub.dart'
    if (dart.library.io) 'offline_open_io.dart';
