import 'package:flutter_riverpod/flutter_riverpod.dart';

class NavIndex extends Notifier<int> {
  @override
  int build() => 0;
  void sec(int i) => state = i;
}

final navIndexProvider = NotifierProvider<NavIndex, int>(NavIndex.new);

const int analizlerSekme = 0;
const int altiliSekme = 1;
const int gecmisSekme = 2;
const int istatistikSekme = 3;
const int detayliSekme = 4;
const int profilSekme = 5;
