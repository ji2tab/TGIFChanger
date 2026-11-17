# XLX 基準接続 設定ガイド（TGIFChanger-Py v2.3.5）

デジピーター（Pi-Star / WPSD）の待機先を **XLX リフレクターのモジュール**に置き、TGIF は必要なときだけつなぐ構成の設定手順です。

## 1. どういう構成か

| | TGIF 直結（従来） | XLX 基準接続 |
|---|---|---|
| 待機先 | TGIF のホームTG | XLX リフレクターのモジュール |
| 別のTGで送信 | TGIF のそのTGにつながる | 同じ（TGIF のそのTGへ直結） |
| 一定時間後 | TGIF のホームTGへ戻る | **TGIF を切断**して、XLX だけの待機に戻る |
| TGIFChanger の役目 | ホームTGへ戻す | TGIF を切断する |

XLX は常時つないだままにして、TGIF 側だけを一時的につないで時間で切ります。XLX を「切り替える」のではありません。

この構成が向いているのは、次のような場合です。

- 待機中の通話を、TGIF の挙動や障害に左右されないようにしたい。
- XLX をハブにして、複数のデジピーターや機器をつなぎたい。
- それでも、無線機のTG指定だけで TGIF の任意のTGへ出られる使い勝手は残したい。

XLX を経由すると、TG番号を相手へ運ぶことができません。XLX は送信の宛先を「どのモジュールか」としてしか扱わないためです。そこで、Pi-Star の DMRGateway を **XLX と TGIF の2方向**に向け、待機TGは XLX へ、それ以外のTGは TGIF へ振り分けます。

## 2. 動作

| 無線機の操作 | 動き |
|---|---|
| 待機TGで送受信 | XLX のモジュールと送受信する |
| 別のTGで送信 | TGIF のそのTGへ直結する |
| 通話終了から `RESTORE_DELAY` 秒後 | TGIFChanger が TGIF を切断（TG4000）する。XLX だけの待機に戻る |

## 3. 前提

- MMDVMHost が DMRGateway 経由で動いていること（`/etc/mmdvmhost` の `[DMR Network]` が `Address=127.0.0.1`）。
- DMRGateway に TGIF の接続があり、`PassAllTG` が有効であること。
- 接続先の XLX リフレクターが、XLX の接続先リスト（`/usr/local/etc/XLXHosts.txt`）に載っていること。載っていない場合は、`/root/XLXHosts.txt` に `<番号>;<ホスト名またはIP>;4004` の形で追加します（Pi-Star の定期更新で消えません）。
- TGIFChanger-Py v2.3.5 以降。

## 4. 設定

以下の例では、次の値を使います。自分の環境の値に読み替えてください。

| 項目 | 例の値 |
|---|---|
| XLX リフレクター | 950 |
| モジュール | A |
| 待機TG | 6 |
| これまで待機TGを書き換えていた TGIF のTG | 12345 |

作業はすべて Pi-Star のターミナルで行います。Pi-Star は通常読み取り専用なので、最初に書き込み可能にします。

```bash
sudo mount -o remount,rw /
sudo cp /etc/dmrgateway /etc/dmrgateway.bak.$(date +%Y%m%d_%H%M%S)
sudo cp /etc/tgifchanger.conf /etc/tgifchanger.conf.bak.$(date +%Y%m%d_%H%M%S)
```

### 4.1 DMRGateway: XLX 接続を有効にする

```bash
sudo sed -i '/^\[XLX Network\]/,/^\[/ { s/^Enabled=.*/Enabled=1/; s/^Startup=.*/Startup=950/; s/^TG=.*/TG=6/ }' /etc/dmrgateway
```

モジュールを指定します。`Module=` の行がある場合は書き換え、ない場合は `Startup=` の次の行に追加します。

```bash
if sudo sed -n '/^\[XLX Network\]/,/^\[/p' /etc/dmrgateway | grep -q '^Module='; then
  sudo sed -i '/^\[XLX Network\]/,/^\[/ s/^Module=.*/Module=A/' /etc/dmrgateway
else
  sudo sed -i '/^\[XLX Network\]/,/^\[/ s/^Startup=.*/&\nModule=A/' /etc/dmrgateway
fi
```

`[XLX Network]` の `TG` が待機TGです。このTGで送信した音声は XLX へ送られ、XLX からの音声もこのTGで電波に出ます。`Id` は7桁の DMR ID にしてください。XLX は9桁の ID を受け付けません。

### 4.2 DMRGateway: 待機TGを TGIF へ書き換える規則を削除する

これまで待機TGを TGIF のTGへ書き換えていた規則（例: `TGRewrite0=1,6,1,12345,1`、`TGRewrite1=2,6,2,12345,1`）を削除します。

```bash
sudo sed -i '/^TGRewrite[0-9]*=[12],6,[12],12345,/d' /etc/dmrgateway
```

**この規則は必ず削除してください。** 残しておくと、TGIF のそのTGの音声が待機TGとして電波に出ます。

### 4.3 DMRGateway: XLX とブリッジされている TGIF のTGを遮断する（該当する場合のみ）

接続先の XLX のモジュールが、どこかで TGIF のTGとブリッジされている場合は、そのTGをこのデジピーターの TGIF 接続で遮断します。遮断しないと、同じ通話が XLX 経由と TGIF 経由の2通りで届いたり、自分の送信が回り込んで戻ってきたりします。

DMRGateway には特定のTGを止める専用の設定がないので、そのTGを TG4000（切断）へ書き換える規則を置きます。

```bash
sudo sed -i '/^Address=tgif\.network/a TGRewrite90=2,12345,2,4000,1' /etc/dmrgateway
```

規則の番号（例では 90）は、ほかの `TGRewrite` と重ならない番号にしてください。ブリッジされているTGがなければ、この手順は不要です。

### 4.4 TGIFChanger: 待機TGと復帰先を設定する

```bash
sudo tg_change -w 6       # 監視TG = [XLX Network] の TG
sudo tg_change -r 4000    # 復帰先 = TGIF の切断
```

### 4.5 反映する

```bash
sudo systemctl restart dmrgateway
sleep 15
sudo systemctl restart tgifchanger-py
sudo tg_change -4000:2    # 現在 TGIF 側でつながっている TG を切断（スロット2の例）
sudo mount -o remount,ro /
```

## 5. 確認

```bash
sudo grep -i "xlx, " "$(ls -t /var/log/pi-star/DMRGateway-*.log | head -n 1)" | tail -n 3
tg_change --status
journalctl -u tgifchanger-py -n 20 --no-pager
```

| 確認すること | 期待する結果 |
|---|---|
| DMRGateway のログ | `XLX, Logged into the master successfully` と `XLX, Linking to reflector XLX950 A` |
| `tg_change --status` | `"mode": "xlx_base"`、`"xlx": "XLX950 A"`、`"restore_tg": "4000"` |
| TGIFChanger の起動ログ | `MODE=XLX基準接続` と表示され、`⚠️ [設定]` の行がない |
| 待機TGで送信 | XLX 側の相手に届く |
| 別のTGで送信 | TGIF のそのTGとつながり、`RESTORE_DELAY` 秒後に切れる |

TGIFChanger は、起動時とリロード時に次の食い違いを見つけると、ログに `⚠️ [設定]` で始まる警告を出します。

- `WATCH_TG` が `[XLX Network]` の `TG` と一致していない。
- `[XLX Network]` が有効なのに、`RESTORE_TG` が 4000 以外になっている。
- TGIF 接続に、待機TGを別のTGへ書き換える `TGRewrite` が残っている。

## 6. 知っておくこと

- **1回の送信が届くネットワークは1つです。** DMRGateway は、宛先が待機TGなら XLX へ、それ以外なら TGIF へ送ります。同じ送信が XLX と TGIF の両方へ同時に出ることはありません。XLX と TGIF をつなぎたい場合は、別にブリッジが必要です。
- **TGIF で交信中に、XLX の通話が入ることがあります。** XLX は常時つながっているので、TGIF のTGで交信している合間に XLX 側で誰かが話すと、そちらが聞こえます。DMRGateway は直前に使った側を数秒間優先しますが、完全には防げません。
- **Pi-Star のダッシュボードで設定を保存すると、`/etc/dmrgateway` が書き換わることがあります。** 保存後は、`[XLX Network]` と `TGRewrite` の規則を確認してください。
- **待機TGを変えるときは、2か所を揃えます。** DMRGateway の `[XLX Network]` の `TG` と、TGIFChanger の `WATCH_TG` です。

## 7. 元に戻す

バックアップから戻して、TGIF のホームTGにつなぎ直します（ファイル名の日時は、自分のバックアップのものに読み替えてください）。

```bash
sudo mount -o remount,rw /
sudo cp /etc/dmrgateway.bak.<日時> /etc/dmrgateway
sudo cp /etc/tgifchanger.conf.bak.<日時> /etc/tgifchanger.conf
sudo systemctl restart dmrgateway tgifchanger-py
sudo tg_change -12345:2    # ホームTGにつなぎ直す（スロット2の例）
sudo mount -o remount,ro /
```
