//! Research-only CPI instruction construction. This does NOT establish
//! that pReDic allows a third-party program as its caller.
use solana_program::{
    account_info::AccountInfo,
    instruction::{AccountMeta, Instruction},
    program::invoke_signed,
    program_error::ProgramError,
    pubkey::Pubkey,
};

pub const PREDIC: Pubkey = solana_program::pubkey!("pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb");

#[derive(Clone, Debug)]
pub struct Open {
    pub nonce: u64,
    pub side: u8,
    pub reserved11: u8,
    pub slippage_bps: u16,
    pub reserved14: u16,
    pub unknown16: u16,
    pub input_amount: u64,
    pub quoted_output_amount: u64,
    pub fee_account_candidate: [u8;32],
    pub platform_fee_candidate: u64,
}
impl Open {
    pub fn bytes(&self) -> Result<[u8;80], ProgramError> {
        if self.side != b'Y' && self.side != b'N' {
            return Err(ProgramError::InvalidInstructionData);
        }
        let mut b = [0u8;80];
        b[0..8].copy_from_slice(&64u64.to_le_bytes());
        b[8..16].copy_from_slice(&self.nonce.to_le_bytes());
        b[16] = self.side;
        b[17] = self.reserved11;
        b[18..20].copy_from_slice(&self.slippage_bps.to_le_bytes());
        b[20..22].copy_from_slice(&self.reserved14.to_le_bytes());
        b[22..24].copy_from_slice(&self.unknown16.to_le_bytes());
        b[24..32].copy_from_slice(&self.input_amount.to_le_bytes());
        b[32..40].copy_from_slice(&self.quoted_output_amount.to_le_bytes());
        b[40..72].copy_from_slice(&self.fee_account_candidate);
        b[72..80].copy_from_slice(&self.platform_fee_candidate.to_le_bytes());
        Ok(b)
    }
}
pub fn order_pda(user: &Pubkey, market: &Pubkey, nonce: u64) -> (Pubkey,u8) {
    Pubkey::find_program_address(&[
        b"userOrderEscrow", user.as_ref(), market.as_ref(), &nonce.to_le_bytes()
    ], &PREDIC)
}
pub fn invoke_open<'a>(
    args: &Open,
    ordered_metas: Vec<AccountMeta>,
    account_infos: &[AccountInfo<'a>],
    caller_signer_seeds: &[&[&[u8]]],
) -> Result<(),ProgramError> {
    // The signer seeds MUST derive an address owned by the *calling* program.
    // Never try to sign for pReDic's UserOrder PDA here.
    let ix = Instruction { program_id: PREDIC, accounts: ordered_metas, data: args.bytes()?.to_vec() };
    invoke_signed(&ix, account_infos, caller_signer_seeds)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wire_offsets() {
        let x=Open{nonce:0x1122334455667788,side:b'Y',reserved11:0,slippage_bps:120,
            reserved14:0,unknown16:324,input_amount:4_469_939,
            quoted_output_amount:5_000_000,fee_account_candidate:[7;32],platform_fee_candidate:9};
        let b=x.bytes().unwrap();
        assert_eq!(b.len(),80);
        assert_eq!(&b[0..8],&64u64.to_le_bytes());
        assert_eq!(&b[22..24],&324u16.to_le_bytes());
        assert_eq!(&b[24..32],&4_469_939u64.to_le_bytes());
        assert_eq!(&b[72..80],&9u64.to_le_bytes());
    }
    #[test]
    fn invalid_side_rejected() {
        let x=Open{nonce:0,side:0,reserved11:0,slippage_bps:0,reserved14:0,
            unknown16:0,input_amount:0,quoted_output_amount:0,fee_account_candidate:[0;32],platform_fee_candidate:0};
        assert!(x.bytes().is_err());
    }
}

#[cfg(test)]
mod historical_pda_tests {
    use super::*;
    use std::str::FromStr;
    #[test]
    fn two_historical_order_addresses() {
        let market = Pubkey::from_str("GGViDLxL6RRQ4zTydGoiL6NnLugxyDGraydUBAQfo9iX").unwrap();
        let cases = [
            ("F6Yt9m6YCM9dazu9XDT57LhZrGaBsYGge2uNJp4s8kM9",
             13680820813140513569u64, "E6RHT33UpybNumSJPxXMiqGCGaEdhn8Y3h2rAUFaTb7",255u8),
            ("DZSQ2gBecP1qoC1xH24i6M1sJZDkTcyPRUHMJR29kgVv",
             11016964509051642506u64, "5wX9x4a8dvS6NyhdDPNCyRrXvMh5TJu48Qc2s37wDWxF",253u8),
        ];
        for (user,nonce,expected,bump) in cases {
            let (derived,b) = order_pda(&Pubkey::from_str(user).unwrap(),&market,nonce);
            assert_eq!(derived,Pubkey::from_str(expected).unwrap());
            assert_eq!(b,bump);
        }
    }
}
